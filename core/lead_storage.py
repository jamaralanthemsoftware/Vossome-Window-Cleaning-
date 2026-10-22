"""Private uploads: reuse configured Spaces, never the public media directory."""
from pathlib import Path
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from django.core.files.base import ContentFile
from django.utils.deconstruct import deconstructible
from storages.backends.s3 import S3Storage


@deconstructible
class ReplitPrivateStorage(Storage):
    """Use the managed App Storage signer; credentials never enter app code."""
    def signed_url(self, name, method):
        path = f"{settings.PRIVATE_OBJECT_DIR.rstrip('/')}/inquiries/{name}".lstrip("/")
        bucket, object_name = path.split("/", 1)
        body = json.dumps({
            "bucket_name": bucket, "object_name": object_name, "method": method,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }).encode()
        request = Request(
            "http://127.0.0.1:1106/object-storage/signed-object-url",
            data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.load(response)["signed_url"]

    def _save(self, name, content):
        request = Request(self.signed_url(name, "PUT"), data=content.read(), method="PUT", headers={"Content-Type": "image/jpeg"})
        with urlopen(request, timeout=30):
            pass
        return name

    def get_available_name(self, name, max_length=None):
        # All names include a fresh random UUID; no network existence probe.
        return name

    def _open(self, name, mode="rb"):
        with urlopen(self.signed_url(name, "GET"), timeout=30) as response:
            return ContentFile(response.read(), name=name)

    def delete(self, name):
        with urlopen(Request(self.signed_url(name, "DELETE"), method="DELETE"), timeout=30):
            pass

    def size(self, name):
        with urlopen(Request(self.signed_url(name, "HEAD"), method="HEAD"), timeout=30) as response:
            return int(response.headers["Content-Length"])


@deconstructible
class PrivateLeadStorage(Storage):
    """Lazy backend so migrations and test collection never need cloud secrets."""
    def backend(self):
        if getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
            return S3Storage(
                default_acl="private", querystring_auth=True,
                custom_domain=None, location="private-inquiries",
                file_overwrite=False,
            )
        if getattr(settings, "PRIVATE_OBJECT_DIR", ""):
            return ReplitPrivateStorage()
        return FileSystemStorage(
            location=getattr(settings, "PRIVATE_LEAD_ROOT", Path(settings.BASE_DIR) / "private-inquiries"),
            base_url=None,
        )

    def save(self, name, content, max_length=None):
        return self.backend().save(name, content, max_length=max_length)

    def open(self, name, mode="rb"):
        return self.backend().open(name, mode)

    def delete(self, name):
        return self.backend().delete(name)

    def size(self, name):
        return self.backend().size(name)

    def exists(self, name):
        return self.backend().exists(name)

    def url(self, name):
        # No customer-photo public URL. Serve only through a staff-authorized view.
        raise ValueError("Customer photos are private; use the authenticated download view.")


private_lead_storage = PrivateLeadStorage()
