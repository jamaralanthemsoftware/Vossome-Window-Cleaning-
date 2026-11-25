"""Strict, dependency-free reader and validator for the SEO and blog bundle."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from threading import RLock
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

CONTRACT_VERSION = 1
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}-[a-z]{2,4}$")
ITEM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
STRING_FIELDS = (
    "seo_title", "meta_description", "focus_keyword", "slug", "canonical",
    "robots_adv", "og_title", "og_description", "og_image", "og_type",
    "og_url", "twitter_title", "twitter_description", "twitter_card",
)
BOOLEAN_FIELDS = ("noindex", "nofollow")
SEO_FIELDS = STRING_FIELDS + BOOLEAN_FIELDS
SUPPORTED_OG_TYPES = frozenset({"website", "article", "profile"})
SUPPORTED_TWITTER_CARDS = frozenset({"summary", "summary_large_image"})
SUPPORTED_POST_STATUSES = frozenset({"publish", "draft"})
POST_REQUIRED_KEYS = frozenset({"title", "slug", "body_html"})
POST_ALLOWED_KEYS = frozenset({
    "title",
    "slug",
    "summary",
    "body_html",
    "status",
    "published_at",
    "author_name",
    "featured_image",
    "featured_image_alt",
    "topics",
})
ROBOTS_DIRECTIVES = frozenset({
    "noarchive", "nosnippet", "noimageindex", "max-snippet", "max-image-preview",
    "max-video-preview",
})
RESERVED_PATHS = frozenset({
    "admin", "cms", "static", "media", "api", "accounts", "integrations",
    "downloads", "emm", "inquiries", "healthz", "robots.txt", "sitemap.xml",
})
CAPABILITY_KEYS = frozenset(set(SEO_FIELDS) | {"faq", "media", "routing"})


class BundleError(ValueError):
    """Raised when repository content is not a valid SEO bundle."""


_bundle_cache = None
_bundle_cache_fingerprint = None
_bundle_cache_lock = RLock()


def bundle_root():
    configured = getattr(settings, "ANTHEM_SEO_ROOT", None)
    if configured:
        return Path(configured)
    base_dir = Path(settings.BASE_DIR)
    django_site_seo = base_dir / "django_site" / "seo"
    if django_site_seo.exists():
        return django_site_seo
    return base_dir / "seo"


def _keys(value, required, allowed, label):
    if not isinstance(value, dict):
        raise BundleError(f"{label} must be an object")
    unknown = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unknown:
        raise BundleError(f"{label} contains unknown keys: {sorted(unknown)}")
    if missing:
        raise BundleError(f"{label} is missing keys: {sorted(missing)}")


def _string(value, label, *, allow_blank=False):
    if not isinstance(value, str) or (not allow_blank and not value.strip()):
        raise BundleError(f"{label} must be a non-empty string")
    if "\x00" in value:
        raise BundleError(f"{label} contains NUL")
    return value


def _language(value, label):
    _string(value, label)
    if not LANGUAGE_RE.fullmatch(value) or value != value.lower():
        raise BundleError(f"{label} is not a valid lowercase language tag")


def _safe_url(value, label):
    _string(value, label)
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BundleError(f"{label} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise BundleError(f"{label} contains unsafe URL components")
    if any(part in {".", ".."} for part in parsed.path.split("/")):
        raise BundleError(f"{label} contains an unsafe path")
    return value


def _slug(value):
    if value == "":
        return value
    if not SLUG_RE.fullmatch(value) or value in RESERVED_PATHS:
        raise BundleError("slug must be a safe URL leaf segment")
    return value


def _robots(value):
    if value == "":
        return value
    tokens = value.split(",")
    seen = set()
    for token in tokens:
        token = token.strip()
        if not token or token in seen:
            raise BundleError("robots_adv contains an empty or duplicate directive")
        seen.add(token)
        name, _, argument = token.partition(":")
        name = name.strip().lower()
        if name not in ROBOTS_DIRECTIVES:
            raise BundleError(f"unsupported robots directive: {name}")
        if name in {"index", "noindex", "follow", "nofollow"} and argument:
            raise BundleError(f"{name} cannot have an argument")
        if name in {"index", "noindex"} and ({"index", "noindex"} & seen):
            if "index" in seen and "noindex" in seen:
                raise BundleError("robots_adv has conflicting index directives")
        if name in {"follow", "nofollow"} and ({"follow", "nofollow"} & seen):
            if "follow" in seen and "nofollow" in seen:
                raise BundleError("robots_adv has conflicting follow directives")
        if name.startswith("max-") and not argument.strip().lstrip("-").isdigit():
            if name != "max-image-preview" or argument.strip() not in {"none", "standard", "large"}:
                raise BundleError(f"malformed robots directive: {token}")
    return value


def _faq(value):
    if value is None:
        raise BundleError("null is not allowed")
    _keys(value, {"section_title", "faqs"}, {"section_title", "faqs"}, "faq")
    _string(value["section_title"], "faq.section_title", allow_blank=True)
    if not isinstance(value["faqs"], list):
        raise BundleError("faq.faqs must be an array")
    seen = set()
    for index, pair in enumerate(value["faqs"]):
        _keys(pair, {"question", "answer"}, {"question", "answer"}, f"faq.faqs[{index}]")
        question = _string(pair["question"], f"faq.faqs[{index}].question")
        answer = _string(pair["answer"], f"faq.faqs[{index}].answer")
        identity = (question.casefold(), answer.casefold())
        if identity in seen:
            raise BundleError("duplicate FAQ pair")
        seen.add(identity)
    return value


def validate_page(document, *, expected_item=None, expected_language=None, expected_reverse_id=None):
    allowed = {"contract_version", "item_id", "language", "kind", "cms_ref", "seo", "faq"}
    _keys(document, {"contract_version", "item_id", "language", "kind", "cms_ref", "seo"}, allowed, "page")
    if document["contract_version"] != CONTRACT_VERSION:
        raise BundleError("unsupported page contract_version")
    item_id = _string(document["item_id"], "item_id")
    if not ITEM_RE.fullmatch(item_id):
        raise BundleError("item_id is not safe")
    language = document["language"]
    _language(language, "language")
    if expected_item and item_id != expected_item:
        raise BundleError("page item_id does not match manifest binding")
    if expected_language and language != expected_language:
        raise BundleError("page language does not match manifest binding")
    if document["kind"] != "page":
        raise BundleError("page kind must be page")
    _keys(document["cms_ref"], {"reverse_id"}, {"reverse_id"}, "cms_ref")
    _string(document["cms_ref"]["reverse_id"], "cms_ref.reverse_id")
    if expected_reverse_id and document["cms_ref"]["reverse_id"] != expected_reverse_id:
        raise BundleError("page cms_ref.reverse_id does not match manifest binding")
    seo = document["seo"]
    if not isinstance(seo, dict):
        raise BundleError("seo must be an object")
    for key, value in seo.items():
        if key not in SEO_FIELDS:
            raise BundleError(f"seo contains unknown key: {key}")
        if value is None:
            raise BundleError(f"seo.{key} cannot be null")
        if key in STRING_FIELDS:
            if not isinstance(value, str):
                raise BundleError(f"seo.{key} must be a string")
            if key == "slug":
                _slug(value)
            elif key in {"canonical", "og_image", "og_url"} and value:
                _safe_url(value, f"seo.{key}")
            elif key == "robots_adv":
                _robots(value)
            elif key == "og_type" and value and value not in SUPPORTED_OG_TYPES:
                raise BundleError("unsupported og_type")
            elif key == "twitter_card" and value and value not in SUPPORTED_TWITTER_CARDS:
                raise BundleError("unsupported twitter_card")
        elif not isinstance(value, bool):
            raise BundleError(f"seo.{key} must be a boolean")
    if "faq" in document:
        _faq(document["faq"])
    return document


def _safe_asset_or_url(value, label):
    _string(value, label)
    if value.startswith(("http://", "https://")):
        return _safe_url(value, label)
    if (
        not value.startswith(("/static/", "/media/"))
        or value.startswith("//")
        or any(char in value for char in "?#\x00")
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise BundleError(
            f"{label} must be an absolute HTTP(S) URL or a safe /static/ or /media/ path"
        )
    return value


def _iso_datetime(value, label):
    _string(value, label)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BundleError(f"{label} must be a valid ISO-8601 datetime") from exc
    return value


def validate_post(document, *, expected_item=None, expected_language=None, expected_reverse_id=None):
    allowed = {"contract_version", "item_id", "language", "kind", "cms_ref", "post"}
    _keys(document, allowed, allowed, "post document")
    if document["contract_version"] != CONTRACT_VERSION:
        raise BundleError("unsupported post contract_version")
    item_id = _string(document["item_id"], "item_id")
    if not ITEM_RE.fullmatch(item_id):
        raise BundleError("item_id is not safe")
    language = document["language"]
    _language(language, "language")
    if expected_item and item_id != expected_item:
        raise BundleError("post item_id does not match manifest binding")
    if expected_language and language != expected_language:
        raise BundleError("post language does not match manifest binding")
    if document["kind"] != "post":
        raise BundleError("post kind must be post")
    _keys(document["cms_ref"], {"reverse_id"}, {"reverse_id"}, "cms_ref")
    reverse_id = _string(document["cms_ref"]["reverse_id"], "cms_ref.reverse_id")
    if expected_reverse_id and reverse_id != expected_reverse_id:
        raise BundleError("post cms_ref.reverse_id does not match manifest binding")
    post = document["post"]
    _keys(post, POST_REQUIRED_KEYS, POST_ALLOWED_KEYS, "post")
    for key, value in post.items():
        if value is None:
            raise BundleError(f"post.{key} cannot be null")
    title = _string(post["title"], "post.title")
    if len(title.strip()) > 240:
        raise BundleError("post.title exceeds 240 characters")
    slug = _string(post["slug"], "post.slug")
    _slug(slug)
    body_html = _string(post["body_html"], "post.body_html")
    if len(body_html) > 200000:
        raise BundleError("post.body_html exceeds maximum length")
    from .sanitize import safe_html as _safe_html

    post["body_html"] = _safe_html(body_html)
    if "summary" in post:
        summary = _string(post["summary"], "post.summary", allow_blank=True)
        if len(summary) > 500:
            raise BundleError("post.summary exceeds 500 characters")
    if "status" in post:
        status = _string(post["status"], "post.status")
        if status not in SUPPORTED_POST_STATUSES:
            raise BundleError("post.status must be publish or draft")
    if "published_at" in post:
        published_at = _string(post["published_at"], "post.published_at", allow_blank=True)
        if published_at:
            _iso_datetime(published_at, "post.published_at")
    if "author_name" in post:
        author_name = _string(post["author_name"], "post.author_name", allow_blank=True)
        if len(author_name) > 255:
            raise BundleError("post.author_name exceeds 255 characters")
    if "featured_image" in post:
        featured_image = _string(post["featured_image"], "post.featured_image", allow_blank=True)
        if featured_image:
            _safe_asset_or_url(featured_image, "post.featured_image")
    if "featured_image_alt" in post:
        featured_image_alt = _string(post["featured_image_alt"], "post.featured_image_alt", allow_blank=True)
        if len(featured_image_alt) > 300:
            raise BundleError("post.featured_image_alt exceeds 300 characters")
    if "topics" in post:
        topics = post["topics"]
        if not isinstance(topics, list) or len(topics) > 20:
            raise BundleError("post.topics must be an array of at most 20 strings")
        for index, topic in enumerate(topics):
            topic_str = _string(topic, f"post.topics[{index}]")
            if len(topic_str.strip()) > 100:
                raise BundleError(f"post.topics[{index}] exceeds 100 characters")
    return document


def validate_manifest(manifest):
    allowed = {
        "contract_version", "site_id", "cms", "content_root", "supported_languages",
        "page_schema_version", "connector_compatibility", "operations", "capabilities", "bindings",
    }
    _keys(manifest, allowed, allowed, "manifest")
    if manifest["contract_version"] != CONTRACT_VERSION or manifest["page_schema_version"] != CONTRACT_VERSION:
        raise BundleError("unsupported manifest or page schema version")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,79}", _string(manifest["site_id"], "site_id")):
        raise BundleError("site_id is not stable")
    if manifest["cms"] != "django-cms":
        raise BundleError("cms must be django-cms")
    _string(manifest["content_root"], "content_root")
    languages = manifest["supported_languages"]
    if not isinstance(languages, list) or not languages:
        raise BundleError("supported_languages must be a non-empty array")
    for language in languages:
        _language(language, "supported_languages")
    _keys(manifest["connector_compatibility"], {"minimum", "maximum"}, {"minimum", "maximum"}, "connector_compatibility")
    if not isinstance(manifest["operations"], list) or not manifest["operations"] or any(
        not isinstance(operation, str) or operation not in {"read", "validate", "render"}
        for operation in manifest["operations"]
    ):
        raise BundleError("operations must list supported read/validate/render operations")
    capabilities = manifest["capabilities"]
    _keys(capabilities, CAPABILITY_KEYS, CAPABILITY_KEYS, "capabilities")
    if any(not isinstance(value, bool) for value in capabilities.values()):
        raise BundleError("capabilities values must be boolean")
    if manifest["content_root"] != "seo/pages":
        raise BundleError("content_root must be seo/pages")
    bindings = manifest["bindings"]
    if not isinstance(bindings, list):
        raise BundleError("bindings must be an array")
    identities, refs = set(), set()
    for index, binding in enumerate(bindings):
        _keys(binding, {"item_id", "language", "kind", "cms_ref"}, {"item_id", "language", "kind", "cms_ref"}, f"bindings[{index}]")
        item_id, language = binding["item_id"], binding["language"]
        if not ITEM_RE.fullmatch(item_id):
            raise BundleError(f"bindings[{index}].item_id is not safe")
        _language(language, f"bindings[{index}].language")
        if language not in languages or binding["kind"] != "page":
            raise BundleError("binding has unsupported language or kind")
        _keys(binding["cms_ref"], {"reverse_id"}, {"reverse_id"}, f"bindings[{index}].cms_ref")
        reverse_id = _string(binding["cms_ref"]["reverse_id"], "binding reverse_id")
        identity = (item_id, language)
        if identity in identities or (language, reverse_id) in refs:
            raise BundleError("duplicate page identity or CMS binding")
        identities.add(identity)
        refs.add((language, reverse_id))
    return manifest


def _bundle_fingerprint(root):
    paths = [root / "manifest.json", root / "redirects.json"]
    page_root = root / "pages"
    if page_root.exists():
        paths.extend(sorted(page_root.glob("*.json")))
    post_root = root / "posts"
    if post_root.exists():
        paths.extend(sorted(post_root.glob("*.json")))
    fingerprint = []
    for path in paths:
        try:
            stat = path.stat()
            fingerprint.append((str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino))
        except OSError:
            fingerprint.append((str(path), None, None))
    return tuple(fingerprint)


def clear_bundle_cache():
    global _bundle_cache, _bundle_cache_fingerprint
    with _bundle_cache_lock:
        _bundle_cache = None
        _bundle_cache_fingerprint = None


def load_bundle(force_reload=False):
    global _bundle_cache, _bundle_cache_fingerprint
    root = bundle_root()
    fingerprint = _bundle_fingerprint(root)
    with _bundle_cache_lock:
        if not force_reload and _bundle_cache is not None and fingerprint == _bundle_cache_fingerprint:
            return _bundle_cache
        bundle = _load_bundle_uncached(root)
        _bundle_cache = bundle
        _bundle_cache_fingerprint = fingerprint
        return bundle


def _load_bundle_uncached(root):
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"cannot read manifest: {exc}") from exc
    validate_manifest(manifest)
    pages = {}
    page_root = root / "pages"
    if page_root.exists():
        for path in sorted(page_root.glob("*.json")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                path.resolve().relative_to(page_root.resolve())
            except ValueError as exc:
                raise BundleError(f"page path escapes content root: {path.name}") from exc
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BundleError(f"cannot read {path.name}: {exc}") from exc
            binding = next((item for item in manifest["bindings"] if item["item_id"] == document.get("item_id") and item["language"] == document.get("language")), None)
            if binding is None:
                raise BundleError(f"{path.name} has no manifest binding")
            validate_page(
                document,
                expected_item=binding["item_id"],
                expected_language=binding["language"],
                expected_reverse_id=binding["cms_ref"]["reverse_id"],
            )
            key = (document["item_id"], document["language"])
            if key in pages:
                raise BundleError("duplicate page document")
            pages[key] = document
    posts = {}
    post_slugs = set()
    post_root = root / "posts"
    if post_root.exists():
        for path in sorted(post_root.glob("*.json")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                path.resolve().relative_to(post_root.resolve())
            except ValueError as exc:
                raise BundleError(f"post path escapes posts root: {path.name}") from exc
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BundleError(f"cannot read {path.name}: {exc}") from exc
            binding = next((item for item in manifest["bindings"] if item["item_id"] == document.get("item_id") and item["language"] == document.get("language")), None)
            if binding is None:
                raise BundleError(f"{path.name} has no manifest binding")
            validate_post(
                document,
                expected_item=binding["item_id"],
                expected_language=binding["language"],
                expected_reverse_id=binding["cms_ref"]["reverse_id"],
            )
            key = (document["item_id"], document["language"])
            if key in posts:
                raise BundleError("duplicate post document")
            slug_key = (document["language"], document["post"]["slug"])
            if slug_key in post_slugs:
                raise BundleError(f"duplicate blog post slug: {document['post']['slug']}")
            post_slugs.add(slug_key)
            posts[key] = document
    redirects = []
    redirects_path = root / "redirects.json"
    if redirects_path.exists():
        try:
            redirects = json.loads(redirects_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleError(f"cannot read redirects: {exc}") from exc
        if not isinstance(redirects, list):
            raise BundleError("redirects.json must contain an array")
        for index, item in enumerate(redirects):
            _keys(item, {"from", "to", "language"}, {"from", "to", "language"}, f"redirects[{index}]")
            _language(item["language"], f"redirects[{index}].language")
            for key in ("from", "to"):
                value = _string(item[key], f"redirects[{index}].{key}")
                if (
                    not value.startswith("/")
                    or value.startswith("//")
                    or ".." in value
                    or value == "/"
                    or any(char in value for char in "?#\x00")
                ):
                    raise BundleError("redirect paths must be safe non-homepage paths")
                first_segment = value.strip("/").split("/", 1)[0]
                if first_segment in RESERVED_PATHS:
                    raise BundleError("redirect uses a reserved path")
    _validate_routes(manifest, pages, redirects)
    payload_pages = {
        f"{item_id}.{language}": document
        for (item_id, language), document in pages.items()
    }
    payload = json.dumps(
        {"manifest": manifest, "pages": payload_pages, "redirects": redirects},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "manifest": manifest,
        "pages": pages,
        "posts": posts,
        "redirects": redirects,
        "digest": hashlib.sha256(payload).hexdigest(),
    }


def _validate_routes(manifest, pages, redirects):
    for binding in manifest["bindings"]:
        document = pages.get((binding["item_id"], binding["language"]))
        slug = document.get("seo", {}).get("slug") if document else None
        if slug:
            if binding["cms_ref"]["reverse_id"] in {"page-home", "home", "coastal-home"}:
                raise BundleError("homepage slug overrides are not supported")
            if slug in RESERVED_PATHS:
                raise BundleError("slug uses a reserved path")
    by_from = {}
    for item in redirects:
        key = (item["language"], item["from"])
        if item["from"] == item["to"]:
            raise BundleError("redirect loop")
        if key in by_from:
            raise BundleError("duplicate redirect source")
        by_from[key] = item["to"]
    for item in redirects:
        if (item["language"], item["to"]) in by_from:
            raise BundleError("redirects must be single-hop to current paths")
    for language, source in by_from:
        seen = set()
        current = source
        while (language, current) in by_from:
            if current in seen:
                raise BundleError("redirect loop")
            seen.add(current)
            current = by_from[(language, current)]


def bundle_digest():
    try:
        return load_bundle()["digest"]
    except BundleError:
        return None
