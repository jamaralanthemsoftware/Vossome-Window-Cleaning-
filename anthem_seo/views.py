"""Read-only discovery endpoints and route dispatch for djangocms-master-template."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import struct
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.utils.html import strip_tags
from django.views.decorators.http import require_GET

from .contract import BundleError, load_bundle
from .records import all_cms_records, record_for_reverse_id
from .resolver import public_site_url, resolve_page
from .routing import effective_path, route_for_path


IMAGE_EXTENSIONS = frozenset({
    ".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp",
})


def _expected_token():
    token = (
        os.environ.get("ANTHEM_SEO_DISCOVERY_TOKEN")
        or getattr(settings, "ANTHEM_SEO_DISCOVERY_TOKEN", "")
    ).strip()
    if token:
        return token
    from .emm import resolve_emm_config

    return resolve_emm_config()["secret"]


def _authorized(request):
    expected = _expected_token()
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    scheme, _, provided = header.partition(" ")
    if scheme.lower() != "bearer" or not provided.strip():
        return False
    return hmac.compare_digest(provided.strip().encode(), expected.encode())


def _no_store(response):
    response["Cache-Control"] = "no-store"
    return response


def _auth_error():
    if not _expected_token():
        return _no_store(
            JsonResponse(
                {"detail": "SEO discovery token is not configured."},
                status=503,
            )
        )
    return _no_store(
        JsonResponse({"detail": "Authentication required."}, status=401)
    )


def _bundle():
    try:
        return load_bundle()
    except BundleError as exc:
        return _no_store(
            JsonResponse(
                {"detail": "SEO bundle is invalid.", "error": str(exc)},
                status=503,
            )
        )


def _analysis_content(record):
    plain = " ".join(strip_tags(record.body_html or "").split())
    changed_iso = (
        record.changed_date.isoformat() if record.changed_date else ""
    )
    revision = (
        f"record:{record.pk}:{changed_iso}:{record.title}:"
        f"{record.page_title}:{record.meta_description}:{plain[:2000]}"
    )
    return plain[:10000], revision


def managed_page(request, seo_path):
    """Dispatch changed bound paths to the underlying core views."""
    route = route_for_path(f"/{seo_path.strip('/')}/")
    if route is None:
        raise Http404("No page matches the given query.")
    from core import views as core_views

    record = route.page
    request.anthem_seo_reverse_id = record.reverse_id
    handlers = {
        "page-home": core_views.home,
        "page-about": core_views.about,
        "page-services": core_views.services,
        "page-commercial": core_views.commercial,
        "page-faq": core_views.faq,
        "page-contact": core_views.contact,
        "page-blog": core_views.blog_list,
    }
    if record.reverse_id in handlers:
        return handlers[record.reverse_id](request)
    cms_slug = record.cms_path.strip("/").split("/")[-1]
    if record.model_kind == "service":
        return core_views.ServiceDetailView.as_view()(request, slug=cms_slug)
    if record.model_kind == "blog":
        return core_views.BlogPostDetailView.as_view()(request, slug=cms_slug)
    if record.model_kind == "page":
        return core_views.PageDetailView.as_view()(request, slug=cms_slug)
    raise Http404("No page matches the given query.")


def _page_payload(record, *, detail=False, bundle=None):
    if record is None:
        return None
    bundle = bundle or load_bundle()
    url = effective_path(record, bundle=bundle)
    public_url = f"{public_site_url()}{url}" if url else None
    public = bool(record.is_public)
    resolved = resolve_page(record, record, public_url, is_public=public)
    analysis_content, revision_content = _analysis_content(record)
    binding = (
        next(
            (
                b
                for b in bundle["manifest"]["bindings"]
                if b["cms_ref"]["reverse_id"] == record.reverse_id
                and b["language"] == "en-us"
            ),
            None,
        )
        if bundle
        else None
    )
    managed = binding is not None
    if managed:
        item_id = binding["item_id"]
    else:
        item_id = f"cms:{record.reverse_id}"
        resolved["raw"] = {}
        resolved["source"] = {key: "cms" for key in resolved["effective"]}
    payload = {
        "item_id": item_id,
        "managed": managed,
        "git_write": False,
        "capabilities": {"read": True, "write": False},
        "language": "en-us",
        "kind": "page",
        "title": record.title,
        "url": public_url,
        "reverse_id": record.reverse_id,
        "status": "published" if public else "draft",
        "modified": (
            record.changed_date.isoformat() if record.changed_date else None
        ),
        "content_revision": hashlib.sha256(
            revision_content.encode()
        ).hexdigest()[:16],
        "seo": {
            "raw": resolved["raw"],
            "defaults": resolved["defaults"],
            "effective": resolved["effective"],
            "source": resolved["source"],
        },
        "faq": {
            "state": resolved["faq_state"],
            "value": resolved["faq"],
            "conflict": resolved["faq_conflict"],
        },
    }
    if detail:
        payload["analysis"] = resolved["analysis"]
        payload["content"] = {
            "title": record.title,
            "page_title": record.page_title,
            "meta_description": record.meta_description,
            "text": analysis_content,
        }
    return payload


def _paginate(request, values, key="results", metadata=None):
    try:
        page_number = max(1, int(request.GET.get("page", "1")))
        page_size = min(100, max(1, int(request.GET.get("page_size", "25"))))
    except ValueError:
        return _no_store(
            JsonResponse(
                {"detail": "page and page_size must be integers."},
                status=400,
            )
        )
    paginator = Paginator(values, page_size)
    page = paginator.get_page(page_number)
    body = {
        key: list(page.object_list),
        "pagination": {
            "page": page.number,
            "page_size": page_size,
            "pages": paginator.num_pages,
            "total": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
    }
    if metadata:
        body.update(metadata)
    return _no_store(JsonResponse(body))


@require_GET
def capabilities(request):
    if not _authorized(request):
        return _auth_error()
    bundle = _bundle()
    if isinstance(bundle, JsonResponse):
        return bundle
    return _no_store(
        JsonResponse({
            "site_id": bundle["manifest"]["site_id"],
            "cms": bundle["manifest"]["cms"],
            "contract_version": bundle["manifest"]["contract_version"],
            "operations": bundle["manifest"]["operations"],
            "capabilities": bundle["manifest"]["capabilities"],
            "bundle_digest": bundle["digest"],
            "revision": bundle["digest"],
        })
    )


@require_GET
def site_revision(request):
    if not _authorized(request):
        return _auth_error()
    bundle = _bundle()
    if isinstance(bundle, JsonResponse):
        return bundle
    return _no_store(
        JsonResponse({
            "site_id": bundle["manifest"]["site_id"],
            "contract_version": bundle["manifest"]["contract_version"],
            "bundle_digest": bundle["digest"],
            "revision": bundle["digest"],
        })
    )


@require_GET
def pages(request):
    if not _authorized(request):
        return _auth_error()
    bundle = _bundle()
    if isinstance(bundle, JsonResponse):
        return bundle
    query = request.GET.get("search", "").strip().casefold()
    payload = []
    for record in all_cms_records():
        path = effective_path(record, bundle=bundle) or ""
        binding = next(
            (
                b
                for b in bundle["manifest"]["bindings"]
                if b["cms_ref"]["reverse_id"] == record.reverse_id
                and b["language"] == "en-us"
            ),
            None,
        )
        item_id = (
            binding["item_id"] if binding else f"cms:{record.reverse_id}"
        )
        if query and not any(
            query in value.casefold()
            for value in (
                item_id,
                record.reverse_id or "",
                record.title or "",
                path,
            )
        ):
            continue
        item = _page_payload(record, bundle=bundle)
        if item is not None:
            payload.append(item)
    response = _paginate(
        request,
        payload,
        metadata={"bundle_digest": bundle["digest"], "revision": bundle["digest"]},
    )
    if response.status_code == 200:
        response.headers["X-Anthem-SEO-Digest"] = bundle["digest"]
    return response


@require_GET
def page_detail(request, item_id):
    if not _authorized(request):
        return _auth_error()
    bundle = _bundle()
    if isinstance(bundle, JsonResponse):
        return bundle
    binding = next(
        (
            binding
            for binding in bundle["manifest"]["bindings"]
            if binding["item_id"] == item_id and binding["language"] == "en-us"
        ),
        None,
    )
    record = (
        record_for_reverse_id(binding["cms_ref"]["reverse_id"])
        if binding
        else None
    )
    item = _page_payload(record, detail=True, bundle=bundle) if record else None
    if item is None:
        return _no_store(
            JsonResponse({"detail": "Bound page not found."}, status=404)
        )
    item["bundle_digest"] = bundle["digest"]
    return _no_store(JsonResponse(item))


def _asset_roots():
    roots = []
    for static_dir in getattr(settings, "STATICFILES_DIRS", []):
        path = Path(static_dir)
        if path.exists():
            roots.append((path, settings.STATIC_URL, "static"))
    media_root = getattr(settings, "MEDIA_ROOT", None)
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    if media_root and Path(media_root).exists():
        roots.append((Path(media_root), media_url, "media"))
    return roots


def _png_dimensions(header):
    if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", header[16:24])
    return None, None


def _gif_dimensions(header):
    if len(header) >= 10 and header[:6] in {b"GIF87a", b"GIF89a"}:
        return struct.unpack("<HH", header[6:10])
    return None, None


def _jpeg_dimensions(handle):
    handle.seek(0)
    if handle.read(2) != b"\xff\xd8":
        return None, None
    while True:
        marker_start = handle.read(1)
        if not marker_start:
            return None, None
        while marker_start == b"\xff":
            marker = handle.read(1)
            if not marker:
                return None, None
            if marker != b"\xff":
                break
        else:
            continue
        if marker in {b"\xd8", b"\xd9"}:
            continue
        length_bytes = handle.read(2)
        if len(length_bytes) != 2:
            return None, None
        segment_length = struct.unpack(">H", length_bytes)[0]
        if segment_length < 2:
            return None, None
        if marker in {
            b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7",
            b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf",
        }:
            frame = handle.read(5)
            if len(frame) != 5:
                return None, None
            height, width = struct.unpack(">HH", frame[1:5])
            return width, height
        handle.seek(segment_length - 2, os.SEEK_CUR)


def _image_dimensions(path: Path, mime_type: str):
    try:
        with path.open("rb") as handle:
            header = handle.read(32)
            if mime_type == "image/png":
                return _png_dimensions(header)
            if mime_type == "image/gif":
                return _gif_dimensions(header)
            if mime_type == "image/jpeg":
                return _jpeg_dimensions(handle)
    except OSError:
        return None, None
    return None, None


@require_GET
def media(request):
    if not _authorized(request):
        return _auth_error()
    results = []
    query = request.GET.get("search", "").strip().casefold()
    base_url = public_site_url()
    for source_root, url_root, source_name in _asset_roots():
        try:
            resolved_root = source_root.resolve()
        except OSError:
            continue
        count = 0
        for directory, dirnames, filenames in os.walk(
            source_root, topdown=True, followlinks=False
        ):
            dirnames[:] = [
                name
                for name in dirnames
                if not (Path(directory) / name).is_symlink()
            ]
            for filename in sorted(filenames):
                if count >= 5000:
                    break
                if filename.startswith("."):
                    continue
                candidate = Path(directory) / filename
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                try:
                    resolved = candidate.resolve()
                    relative = resolved.relative_to(resolved_root).as_posix()
                except (OSError, ValueError):
                    continue
                count += 1
                title = candidate.stem.replace("-", " ").replace("_", " ").strip()
                if query and query not in relative.casefold() and query not in title.casefold():
                    continue
                mime_type, _ = mimetypes.guess_type(candidate.name)
                mime_type = mime_type or "application/octet-stream"
                width, height = _image_dimensions(resolved, mime_type)
                encoded_rel = "/".join(quote(part) for part in relative.split("/"))
                if url_root.startswith(("http://", "https://")):
                    public_asset_url = f"{url_root.rstrip('/')}/{encoded_rel}"
                else:
                    public_asset_url = (
                        f"{base_url}/{url_root.strip('/')}/{encoded_rel}"
                    )
                results.append({
                    "id": f"{source_name}:{relative}",
                    "url": public_asset_url,
                    "thumbnail": public_asset_url,
                    "title": title or candidate.name,
                    "alt": title or candidate.name,
                    "mime_type": mime_type,
                    "width": width,
                    "height": height,
                    "source": source_name,
                })
    return _paginate(request, results, key="media")
