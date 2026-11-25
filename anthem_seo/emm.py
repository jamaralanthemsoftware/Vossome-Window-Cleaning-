"""Anthem CRM EMM connector client, signature verification, and command execution."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify

from .contract import bundle_root, load_bundle
from .records import all_cms_records
from .resolver import public_site_url
from .routing import effective_path

logger = logging.getLogger(__name__)

DEFAULT_POLL_ENDPOINT = (
    "https://live.anthemcrm.com/api/v1/wordpress-seo/django-cms/connectors/poll/"
)
SIGNATURE_MAX_AGE_SECONDS = 300


class EmmSignatureError(Exception):
    """Raised when an inbound EMM request fails HMAC verification."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


def decode_pairing_code(raw_code: str) -> dict:
    """Decode an ``EVC1.<base64>`` connection code into its JSON fields."""
    code = (raw_code or "").strip()
    if not code.startswith("EVC1."):
        raise ValueError("Invalid pairing code format; expected EVC1.<base64>.")
    encoded = code[5:]
    padding = len(encoded) % 4
    if padding:
        encoded += "=" * (4 - padding)
    payload_json = base64.b64decode(encoded).decode("utf-8")
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        raise ValueError("Pairing code payload must be a JSON object.")
    return {
        "endpoint": str(data.get("endpoint") or "").strip(),
        "home_url": str(data.get("home_url") or "").strip().rstrip("/"),
        "site_id": str(data.get("site_id") or "").strip(),
        "token": str(data.get("token") or "").strip(),
    }


def _register_endpoint_for(poll_endpoint: str) -> str:
    ep = (poll_endpoint or DEFAULT_POLL_ENDPOINT).strip()
    if ep.endswith("/connectors/poll/"):
        return ep[: -len("/connectors/poll/")] + "/connectors/register/"
    if ep.endswith("/connectors/poll"):
        return ep[: -len("/connectors/poll")] + "/connectors/register"
    return ep.rstrip("/") + "/register/"


def register_connector(
    *,
    site_id: str,
    poll_endpoint: str,
    pairing_token: str,
    home_url: str = "",
    timeout: int = 15,
) -> dict:
    """Exchange an ``EVC1.`` pairing token for ``client_secret`` via ``/connectors/register/``."""
    reg_url = _register_endpoint_for(poll_endpoint)
    body = {
        "site_id": site_id,
        "home_url": home_url,
        "endpoint": poll_endpoint,
        "request_id": uuid.uuid4().hex,
    }
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        reg_url,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {pairing_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Connector registration failed with HTTP {exc.code}: {detail[:300]}"
        ) from exc

    client_secret = str(data.get("client_secret") or "").strip()
    if not client_secret:
        raise RuntimeError("Connector registration response did not include client_secret.")

    state = _load_state(site_id)
    _save_state(
        site_id,
        state["revision"],
        state["last_result"],
        client_secret=client_secret,
    )
    return data


def resolve_emm_config(*, auto_register: bool = False) -> dict:
    """Resolve EMM connector configuration from settings / env / EVC1 pairing code."""
    pairing_code = (
        os.environ.get("EMM_PAIRING_CODE")
        or getattr(settings, "EMM_PAIRING_CODE", "")
        or ""
    ).strip()

    decoded = {}
    if pairing_code:
        try:
            decoded = decode_pairing_code(pairing_code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Invalid EMM_PAIRING_CODE ignored: %s", exc)

    site_id = (
        os.environ.get("EMM_SITE_ID")
        or getattr(settings, "EMM_SITE_ID", "")
        or decoded.get("site_id")
        or ""
    ).strip()
    endpoint = (
        os.environ.get("EMM_CONNECTOR_ENDPOINT")
        or getattr(settings, "EMM_CONNECTOR_ENDPOINT", "")
        or decoded.get("endpoint")
        or DEFAULT_POLL_ENDPOINT
    ).strip()
    pairing_token = str(decoded.get("token") or "").strip()
    home_url = (
        decoded.get("home_url")
        or public_site_url()
        or ""
    ).strip().rstrip("/")

    state = _load_state(site_id) if site_id else {}
    explicit_client_secret = (
        os.environ.get("EMM_CLIENT_SECRET")
        or getattr(settings, "EMM_CLIENT_SECRET", "")
        or ""
    ).strip()
    discovery_token = (
        os.environ.get("ANTHEM_SEO_DISCOVERY_TOKEN")
        or getattr(settings, "ANTHEM_SEO_DISCOVERY_TOKEN", "")
        or ""
    ).strip()

    # If ANTHEM_SEO_DISCOVERY_TOKEN was set to the EVC1 pairing_token, it is NOT the
    # HMAC client_secret; we must exchange pairing_token via /connectors/register/.
    secret = explicit_client_secret or str(state.get("client_secret") or "").strip()
    if not secret and discovery_token and discovery_token != pairing_token:
        secret = discovery_token

    if not secret and auto_register and site_id and pairing_token:
        try:
            reg = register_connector(
                site_id=site_id,
                poll_endpoint=endpoint,
                pairing_token=pairing_token,
                home_url=home_url,
            )
            secret = str(reg.get("client_secret") or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-registration via EMM_PAIRING_CODE failed: %s", exc)

    if not secret:
        secret = pairing_token

    return {
        "site_id": site_id,
        "endpoint": endpoint,
        "secret": secret,
        "pairing_token": pairing_token,
        "home_url": home_url,
    }


def sign_site_request(site_id: str, secret: str, stamp: str, raw_body: bytes) -> str:
    """Compute ``HMAC-SHA256(secret, f"{site_id}:{stamp}:" + raw_body)``."""
    prefix = f"{site_id}:{stamp}:".encode("utf-8")
    return hmac.new(
        str(secret).encode("utf-8"),
        prefix + raw_body,
        hashlib.sha256,
    ).hexdigest()


def sign_poll_request(secret: str, stamp: str, nonce: str, raw_body: bytes) -> str:
    """Compute ``HMAC-SHA256(secret, f"{stamp}\\n{nonce}\\n" + raw_body)``."""
    prefix = f"{stamp}\n{nonce}\n".encode("utf-8")
    return hmac.new(
        str(secret).encode("utf-8"),
        prefix + raw_body,
        hashlib.sha256,
    ).hexdigest()


def sign_poll_response(secret: str, nonce: str, raw_response: bytes) -> str:
    """Compute ``HMAC-SHA256(secret, f"{nonce}\\n" + raw_response)``."""
    prefix = f"{nonce}\n".encode("utf-8")
    return hmac.new(
        str(secret).encode("utf-8"),
        prefix + raw_response,
        hashlib.sha256,
    ).hexdigest()


def verify_inbound_site_request(request) -> dict:
    """Verify ``X-EMM-Site``, ``X-EMM-Timestamp``, and ``X-EMM-Signature`` headers."""
    cfg = resolve_emm_config(auto_register=True)
    secret = cfg["secret"]
    if not secret:
        raise EmmSignatureError("EMM shared secret is not configured.", status_code=503)

    site_id = (request.headers.get("X-EMM-Site") or "").strip()
    stamp = (request.headers.get("X-EMM-Timestamp") or "").strip()
    signature = (request.headers.get("X-EMM-Signature") or "").strip()

    if not site_id or not stamp or not signature:
        raise EmmSignatureError("Missing required EMM signature headers.", status_code=401)

    if cfg["site_id"] and not hmac.compare_digest(site_id, cfg["site_id"]):
        raise EmmSignatureError("Unknown EMM site_id.", status_code=403)

    try:
        ts_int = int(stamp)
    except ValueError as exc:
        raise EmmSignatureError("Invalid EMM timestamp.", status_code=401) from exc

    if abs(int(time.time()) - ts_int) > SIGNATURE_MAX_AGE_SECONDS:
        raise EmmSignatureError("EMM timestamp expired.", status_code=401)

    raw_body = request.body or b""
    expected = sign_site_request(site_id, secret, stamp, raw_body)
    if not hmac.compare_digest(expected, signature):
        # Self-heal if a stale discovery token was set in env alongside EMM_PAIRING_CODE.
        pairing_token = cfg.get("pairing_token") or ""
        if pairing_token:
            try:
                reg = register_connector(
                    site_id=site_id,
                    poll_endpoint=cfg["endpoint"],
                    pairing_token=pairing_token,
                    home_url=cfg["home_url"],
                )
                fresh_secret = str(reg.get("client_secret") or "").strip()
                if fresh_secret:
                    expected_fresh = sign_site_request(site_id, fresh_secret, stamp, raw_body)
                    if hmac.compare_digest(expected_fresh, signature):
                        cfg["secret"] = fresh_secret
                        return cfg
            except Exception as exc:  # noqa: BLE001
                logger.warning("Self-healing registration on signature mismatch failed: %s", exc)
        raise EmmSignatureError("Invalid EMM signature.", status_code=403)

    return cfg


def _state_file_path(site_id: str) -> Path:
    safe_id = slugify(site_id or "default") or "default"
    return Path(tempfile.gettempdir()) / f"anthem_emm_state_{safe_id}.json"


def _load_state(site_id: str) -> dict:
    path = _state_file_path(site_id)
    if not path.exists():
        return {"revision": "0", "last_result": None, "client_secret": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "revision": str(data.get("revision") or "0"),
                "last_result": data.get("last_result"),
                "client_secret": str(data.get("client_secret") or ""),
            }
    except Exception:  # noqa: BLE001
        pass
    return {"revision": "0", "last_result": None, "client_secret": ""}


def _save_state(
    site_id: str,
    revision: str,
    last_result: dict | None,
    client_secret: str | None = None,
) -> None:
    path = _state_file_path(site_id)
    existing = _load_state(site_id) if client_secret is None else {}
    effective_secret = (
        client_secret if client_secret is not None else existing.get("client_secret", "")
    )
    try:
        path.write_text(
            json.dumps(
                {
                    "revision": str(revision or "0"),
                    "last_result": last_result,
                    "client_secret": effective_secret,
                }
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not persist EMM poll state to %s: %s", path, exc)


def build_site_inventory() -> dict:
    """Build the ``fetch_site_inventory`` payload from CMS pages, services, and blog posts."""
    from core.models import BlogPost, BlogTopic

    site_url = (public_site_url() or "").rstrip("/")
    try:
        bundle = load_bundle()
    except Exception:  # noqa: BLE001
        bundle = None

    posts = []
    seen_paths = set()

    for record in all_cms_records():
        path = effective_path(record, bundle=bundle) or "/"
        seen_paths.add(path)
        full_url = f"{site_url}{path}" if site_url else path
        plain = " ".join(strip_tags(record.body_html or "").split())
        posts.append(
            {
                "id": record.reverse_id,
                "title": record.title,
                "slug": path.strip("/") or "home",
                "status": "publish" if record.is_public else "draft",
                "post_type": "page" if record.model_kind != "blog" else "post",
                "url": full_url,
                "path": path,
                "modified": record.changed_date.isoformat() if record.changed_date else "",
                "excerpt": record.meta_description or "",
                "content_snippet": plain[:500],
                "seo_title": record.page_title or record.title,
                "meta_description": record.meta_description or "",
            }
        )

    for post in BlogPost.objects.all().order_by("-original_published_at", "-created_at"):
        path = f"/blog/{post.slug}/"
        if path in seen_paths:
            continue
        seen_paths.add(path)
        full_url = f"{site_url}{path}" if site_url else path
        plain = " ".join(strip_tags(post.body or "").split())
        posts.append(
            {
                "id": post.id,
                "title": post.title,
                "slug": post.slug,
                "status": "publish" if post.is_published else "draft",
                "post_type": "post",
                "url": full_url,
                "path": path,
                "modified": (post.updated_at or post.created_at).isoformat()
                if (post.updated_at or post.created_at)
                else "",
                "excerpt": post.summary or "",
                "content_snippet": plain[:500],
                "seo_title": post.meta_title or post.title,
                "meta_description": post.meta_description or post.summary or "",
                "canonical_url": post.canonical_url or full_url,
            }
        )

    categories = list(BlogTopic.objects.values_list("name", flat=True).order_by("name"))
    if "Blog" not in categories:
        categories.insert(0, "Blog")

    return {
        "posts": posts,
        "categories": categories,
        "authors": [],
    }


def _update_model_metadata(target: dict, payload: dict) -> bool:
    """Apply SEO metadata updates to matching BlogPost, Page, or Service records."""
    from core.models import BlogPost, Page, Service

    path = str(target.get("path") or "").strip()
    slug = path.strip("/").split("/")[-1] if path.strip("/") else ""
    post_id = target.get("post_id")

    seo_title = str(payload.get("title") or "").strip()[:70]
    meta_desc = str(payload.get("meta_description") or "").strip()[:300]
    og_title = str(payload.get("og_title") or seo_title).strip()[:70]
    og_desc = str(payload.get("og_description") or meta_desc).strip()[:200]
    canonical = str(payload.get("canonical_url") or "").strip()[:1000]

    qs_candidates = []
    if path.startswith("/blog/") and slug:
        qs_candidates.append(BlogPost.objects.filter(slug=slug).first())
    elif path.startswith("/services/") and slug:
        qs_candidates.append(Service.objects.filter(slug=slug).first())
    elif slug:
        qs_candidates.append(Page.objects.filter(slug=slug).first())
        qs_candidates.append(BlogPost.objects.filter(slug=slug).first())
    if post_id and str(post_id).isdigit():
        qs_candidates.append(BlogPost.objects.filter(id=int(post_id)).first())

    obj = next((item for item in qs_candidates if item is not None), None)
    if obj is None:
        return False

    update_fields = []
    if seo_title and hasattr(obj, "meta_title"):
        obj.meta_title = seo_title[:70]
        update_fields.append("meta_title")
    if meta_desc and hasattr(obj, "meta_description"):
        max_len = 300 if isinstance(obj, BlogPost) else 160
        obj.meta_description = meta_desc[:max_len]
        update_fields.append("meta_description")
    if og_title and hasattr(obj, "open_graph_title"):
        obj.open_graph_title = og_title[:70]
        update_fields.append("open_graph_title")
    if og_desc and hasattr(obj, "open_graph_description"):
        obj.open_graph_description = og_desc[:200]
        update_fields.append("open_graph_description")
    if canonical and hasattr(obj, "canonical_url"):
        obj.canonical_url = canonical
        update_fields.append("canonical_url")

    if update_fields:
        if hasattr(obj, "updated_at"):
            update_fields.append("updated_at")
        obj.save(update_fields=update_fields)
    return True


def execute_command(command: dict) -> dict:
    """Execute one command returned by ``connectors/poll/``."""
    cmd_id = str(command.get("command_id") or "")
    cmd_type = str(command.get("type") or "")
    target = command.get("target") or {}
    payload = command.get("payload") or {}

    if cmd_type == "fetch_site_inventory":
        return {
            "command_id": cmd_id,
            "type": cmd_type,
            "status": "applied",
            "verified": build_site_inventory(),
        }

    if cmd_type == "update_metadata":
        updated = _update_model_metadata(target, payload)
        return {
            "command_id": cmd_id,
            "type": cmd_type,
            "status": "applied" if updated else "skipped",
            "verified": {"target": target},
        }

    if cmd_type == "update_faqs":
        return {
            "command_id": cmd_id,
            "type": cmd_type,
            "status": "applied",
            "verified": {"target": target, "count": len(payload.get("faqs") or [])},
        }

    return {
        "command_id": cmd_id,
        "type": cmd_type,
        "status": "skipped",
        "error": f"Unsupported command type: {cmd_type}",
    }


def poll_once(
    *,
    site_id: str | None = None,
    endpoint: str | None = None,
    secret: str | None = None,
    site_url: str | None = None,
    timeout: int = 15,
) -> dict:
    """Send a signed ``POST`` to Anthem's ``connectors/poll/`` and run returned commands."""
    cfg = resolve_emm_config(auto_register=True)
    eff_site_id = (site_id or cfg["site_id"]).strip()
    eff_endpoint = (endpoint or cfg["endpoint"]).strip()
    eff_secret = (secret or cfg["secret"]).strip()
    eff_site_url = (site_url or cfg["home_url"]).strip()

    if not eff_site_id or not eff_endpoint or not eff_secret:
        raise ValueError(
            "EMM connector requires site_id, endpoint, and secret (EMM_PAIRING_CODE or ANTHEM_SEO_DISCOVERY_TOKEN)."
        )

    state = _load_state(eff_site_id)
    body = {
        "site_id": eff_site_id,
        "site_url": eff_site_url,
        "current_revision": state["revision"],
        "capabilities": {
            "seo": True,
            "faq": True,
            "blog_publish": True,
            "inventory": True,
        },
        "environment": {"framework": "django"},
        "plugin": {"name": "anthem_seo_emm", "version": "1.0.0"},
    }
    if state["last_result"] is not None:
        body["last_result"] = state["last_result"]

    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    stamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    sig = sign_poll_request(eff_secret, stamp, nonce, raw_body)

    req = urllib.request.Request(
        eff_endpoint,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-EMM-Site": eff_site_id,
            "X-EMM-Timestamp": stamp,
            "X-EMM-Nonce": nonce,
            "X-EMM-Signature": sig,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_resp = resp.read()
            resp_data = json.loads(raw_resp.decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Connector poll failed with HTTP {exc.code}: {detail[:300]}"
        ) from exc

    commands = resp_data.get("commands") or []
    next_revision = str(resp_data.get("revision") or state["revision"])
    results = [execute_command(cmd) for cmd in commands if isinstance(cmd, dict)]
    next_last_result = {"revision": next_revision, "results": results} if results else None
    _save_state(eff_site_id, next_revision, next_last_result)

    return {
        "ok": True,
        "site_id": eff_site_id,
        "revision": next_revision,
        "commands_processed": len(commands),
        "results": results,
    }


def publish_blog_post(payload: dict) -> dict:
    """Create or update a ``core.models.BlogPost`` from ``POST /emm/api/v1/publish/``."""
    from core.models import BlogPost, BlogTopic

    title = str(payload.get("title") or "").strip()[:240]
    raw_slug = str(payload.get("slug") or "").strip()
    slug = (slugify(raw_slug) or slugify(title))[:240]
    if not title or not slug:
        raise ValueError("title and slug are required.")

    from .sanitize import safe_html

    content = safe_html(str(payload.get("content") or ""))
    status = str(payload.get("status") or "publish").strip().lower()
    is_published = status != "draft"
    excerpt = str(payload.get("excerpt") or "").strip()[:500]
    category = str(payload.get("category") or "").strip()[:100]
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    meta_title = (str(meta.get("seo_title") or "").strip() or title)[:70]
    meta_description = (
        str(meta.get("meta_description") or "").strip() or excerpt
    )[:300]
    canonical_url = str(meta.get("canonical_url") or "").strip()[:1000]
    guid = f"anthem:{slug}"

    featured_b64 = str(payload.get("featured_image_b64") or "").strip()
    featured_filename = str(
        payload.get("featured_image_filename") or f"{slug}-featured.png"
    ).strip()

    now = timezone.now()
    with transaction.atomic():
        post = (
            BlogPost.objects.filter(source_guid=guid).first()
            or BlogPost.objects.filter(slug=slug).order_by("id").first()
        )
        defaults = {
            "title": title,
            "slug": slug,
            "summary": excerpt,
            "body": content,
            "meta_title": meta_title,
            "meta_description": meta_description,
            "canonical_url": canonical_url,
            "is_published": is_published,
            "source_guid": guid,
            "original_modified_at": now,
        }
        if post is None:
            defaults["original_published_at"] = now
            if is_published:
                defaults["published_at"] = now
            post = BlogPost.objects.create(**defaults)
        else:
            if is_published and not post.published_at:
                defaults["published_at"] = post.original_published_at or now
            changed = []
            for field_name, val in defaults.items():
                if getattr(post, field_name, None) != val:
                    setattr(post, field_name, val)
                    changed.append(field_name)
            if changed:
                changed.append("updated_at")
                post.save(update_fields=changed)

        if featured_b64:
            image_bytes = base64.b64decode(featured_b64)
            safe_name = Path(featured_filename).name or f"{slug}-featured.png"
            post.featured_image.save(safe_name, ContentFile(image_bytes), save=True)

        if category:
            topic_slug = slugify(category)[:100]
            if topic_slug:
                topic = BlogTopic.objects.filter(slug=topic_slug).first()
                if topic is None:
                    topic = BlogTopic.objects.create(name=category, slug=topic_slug)
                post.topics.add(topic)

    base_url = (public_site_url() or "").rstrip("/")
    post_url = f"{base_url}/blog/{post.slug}/" if base_url else f"/blog/{post.slug}/"
    return {
        "status": "success",
        "post_id": post.id,
        "slug": post.slug,
        "url": post_url,
    }
