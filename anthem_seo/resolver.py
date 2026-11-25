"""Resolution of repository overrides over djangocms-master-template metadata."""

from __future__ import annotations

import html
import json
import re

from django.conf import settings
from django.utils.html import strip_tags

from .contract import load_bundle

DEFAULT_SHARE_IMAGE = "/static/images/logo.jpg"


def public_site_url() -> str:
    return str(
        getattr(
            settings,
            "PUBLIC_SITE_URL",
            getattr(settings, "SITE_URL", "http://localhost:8000"),
        )
    ).rstrip("/")


def _safe_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


def _plain(value):
    return re.sub(r"\s+", " ", strip_tags(html.unescape(value or ""))).strip()


def _raw_for(page, language="en-us"):
    bundle = load_bundle()
    reverse_id = getattr(page, "reverse_id", None)
    for binding in bundle["manifest"]["bindings"]:
        if (
            binding["cms_ref"]["reverse_id"] == reverse_id
            and binding["language"] == language
        ):
            return bundle["pages"].get((binding["item_id"], language)), bundle
    return None, bundle


def _cms_slug(page):
    cms_path = getattr(page, "cms_path", "") or ""
    if cms_path and cms_path != "/":
        return cms_path.strip("/").split("/")[-1]
    slug = getattr(page, "slug", "") or ""
    return slug.strip("/")


def _cms_defaults(page, content, public_url, language="en-us"):
    source_obj = content or page
    title = (
        getattr(source_obj, "page_title", "")
        or getattr(source_obj, "title", "")
        or "Client Website"
    )
    description = getattr(source_obj, "meta_description", "") or ""
    og_image_path = getattr(source_obj, "og_image_url", "") or DEFAULT_SHARE_IMAGE
    if og_image_path.startswith(("http://", "https://")):
        og_image = og_image_path
    else:
        og_image = f"{public_site_url()}/{og_image_path.lstrip('/')}"
    return {
        "seo_title": title,
        "meta_description": description,
        "focus_keyword": "",
        "slug": _cms_slug(page),
        "canonical": public_url,
        "robots_adv": "",
        "og_title": title,
        "og_description": description,
        "og_image": og_image,
        "og_type": "website",
        "og_url": public_url,
        "twitter_title": title,
        "twitter_description": description,
        "twitter_card": "summary_large_image",
        "noindex": False,
        "nofollow": False,
    }


def resolve_page(
    page,
    content=None,
    public_url=None,
    *,
    is_public=True,
    language="en-us",
):
    """Return raw/default/effective/source maps and render-ready metadata."""
    raw_document, bundle = _raw_for(page, language)
    raw = (raw_document or {}).get("seo", {})
    defaults = _cms_defaults(page, content, public_url, language)
    effective, source = {}, {}
    for field, default in defaults.items():
        if field not in raw:
            effective[field], source[field] = default, "cms"
        elif isinstance(raw[field], str) and raw[field] == "":
            effective[field], source[field] = default, "fallback"
        else:
            effective[field], source[field] = raw[field], "github"

    for social_field, primary_field in (
        ("og_title", "seo_title"),
        ("og_description", "meta_description"),
        ("twitter_title", "seo_title"),
        ("twitter_description", "meta_description"),
    ):
        if social_field not in raw or raw.get(social_field) == "":
            effective[social_field] = effective[primary_field]
            source[social_field] = "fallback"

    effective["canonical"] = effective["canonical"] or public_url
    if "og_url" not in raw or raw.get("og_url") == "":
        effective["og_url"] = effective["canonical"]
        source["og_url"] = "fallback"

    if bundle and (
        not bundle["manifest"]["capabilities"].get("slug", False)
        or not bundle["manifest"]["capabilities"].get("routing", False)
    ):
        if "slug" in raw:
            effective["slug"] = defaults["slug"]
            source["slug"] = "unsupported"

    public = bool(is_public and public_url)
    if not public:
        effective["noindex"] = True
        effective["nofollow"] = True
        source["noindex"] = source["nofollow"] = "access-policy"

    robots = []
    if effective["noindex"]:
        robots.append("noindex")
    else:
        robots.append("index")
    if effective["nofollow"]:
        robots.append("nofollow")
    else:
        robots.append("follow")
    if effective["robots_adv"]:
        robots.extend(
            part.strip()
            for part in effective["robots_adv"].split(",")
            if part.strip()
        )

    faq_state = "missing"
    managed_faq = None
    if raw_document and "faq" in raw_document:
        managed_faq = raw_document["faq"]
        faq_state = "empty" if not managed_faq["faqs"] else "managed"

    faq_conflict = bool(
        faq_state == "managed" and getattr(page, "has_cms_faq", False)
    )
    return {
        "raw": raw,
        "defaults": defaults,
        "effective": effective,
        "source": source,
        "robots": ", ".join(dict.fromkeys(robots)),
        "is_public": public,
        "faq": managed_faq,
        "faq_state": faq_state,
        "faq_conflict": faq_conflict,
        "bundle": bundle,
        "bundle_digest": bundle["digest"] if bundle else None,
        "analysis": {
            "title_length": len(effective["seo_title"]),
            "description_length": len(effective["meta_description"]),
            "warnings": (
                (
                    ["title exceeds 60 characters"]
                    if len(effective["seo_title"]) > 60
                    else []
                )
                + (
                    ["description exceeds 160 characters"]
                    if len(effective["meta_description"]) > 160
                    else []
                )
            ),
        },
    }


def managed_faq_json(faq, canonical_url):
    if not faq or not faq["faqs"]:
        return None
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "@id": f"{canonical_url}#faqpage",
        "url": canonical_url,
        "mainEntity": [
            {
                "@type": "Question",
                "name": _plain(pair["question"]),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": _plain(pair["answer"]),
                },
            }
            for pair in faq["faqs"]
        ],
    }
    return _safe_json(data)


def _reverse_id_candidates_for_path(path: str) -> list[str]:
    normalized = "/" if not path or path == "/" else "/" + path.strip("/") + "/"
    static_map = {
        "/": ["page-home"],
        "/about/": ["page-about"],
        "/services/": ["page-services"],
        "/commercial-window-cleaning/": ["page-commercial"],
        "/faq/": ["page-faq"],
        "/contact/": ["page-contact"],
        "/blog/": ["page-blog"],
    }
    if normalized in static_map:
        return static_map[normalized]
    parts = normalized.strip("/").split("/")
    if len(parts) == 1 and parts[0]:
        return [f"page-{parts[0]}"]
    if len(parts) == 2 and parts[0] == "services":
        return [f"svc-{parts[1]}"]
    if len(parts) == 2 and parts[0] == "blog":
        return [f"blog-{parts[1]}", f"coastal-blog-{parts[1]}"]
    return []


def resolve_request_overrides(request, language="en-us") -> dict:
    """Zero-DB-query template context resolution for active GitHub SEO documents."""
    try:
        bundle = load_bundle()
    except Exception:
        return {
            "anthem_seo_override": {},
            "managed_faq": None,
            "faq_json_ld": None,
        }
    pages = bundle.get("pages") or {}
    if not pages:
        return {
            "anthem_seo_override": {},
            "managed_faq": None,
            "faq_json_ld": None,
        }

    path = getattr(request, "path", "/") or "/"
    normalized_path = "/" if path == "/" else "/" + path.strip("/") + "/"
    reverse_id = getattr(request, "anthem_seo_reverse_id", None)
    candidates = [reverse_id] if reverse_id else _reverse_id_candidates_for_path(path)
    leaf = path.strip("/").split("/")[-1] if path.strip("/") else ""
    is_blog_detail_path = (
        normalized_path.startswith("/blog/") and normalized_path != "/blog/"
    )

    posts = bundle.get("posts") or {}
    matched_doc = None
    for binding in bundle["manifest"]["bindings"]:
        if binding["language"] != language:
            continue
        doc = pages.get((binding["item_id"], language))
        if not doc:
            continue
        b_rev = binding["cms_ref"]["reverse_id"]
        doc_slug = (doc.get("seo") or {}).get("slug") or ""
        post_doc = posts.get((binding["item_id"], language)) or {}
        post_slug = (post_doc.get("post") or {}).get("slug") or ""
        if (
            b_rev in candidates
            or (doc_slug and doc_slug == leaf)
            or (is_blog_detail_path and post_slug and post_slug == leaf)
        ):
            matched_doc = doc
            break

    if not matched_doc:
        return {
            "anthem_seo_override": {},
            "managed_faq": None,
            "faq_json_ld": None,
        }

    raw_seo = matched_doc.get("seo") or {}
    try:
        canonical_default = request.build_absolute_uri()
    except Exception:
        canonical_default = f"{public_site_url()}{path}"
    canonical = raw_seo.get("canonical") or canonical_default

    override = {}
    for key in (
        "seo_title",
        "meta_description",
        "canonical",
        "og_title",
        "og_description",
        "og_image",
        "og_type",
        "og_url",
        "twitter_title",
        "twitter_description",
        "twitter_card",
    ):
        val = raw_seo.get(key)
        if isinstance(val, str) and val:
            override[key] = val

    if "seo_title" in override:
        override.setdefault("og_title", override["seo_title"])
        override.setdefault("twitter_title", override["seo_title"])
    if "meta_description" in override:
        override.setdefault("og_description", override["meta_description"])
        override.setdefault("twitter_description", override["meta_description"])
    if "canonical" in override:
        override.setdefault("og_url", override["canonical"])

    if any(k in raw_seo for k in ("noindex", "nofollow", "robots_adv")):
        robots = [
            "noindex" if raw_seo.get("noindex") else "index",
            "nofollow" if raw_seo.get("nofollow") else "follow",
        ]
        if raw_seo.get("robots_adv"):
            robots.extend(
                part.strip()
                for part in raw_seo["robots_adv"].split(",")
                if part.strip()
            )
        override["robots"] = ", ".join(dict.fromkeys(robots))

    managed_faq = None
    faq_json_ld = None
    if "faq" in matched_doc and matched_doc["faq"].get("faqs"):
        raw_faq = matched_doc["faq"]
        managed_faq = {
            "section_title": _plain(raw_faq.get("section_title", "")),
            "faqs": [
                {
                    "question": _plain(pair["question"]),
                    "answer": _plain(pair["answer"]),
                }
                for pair in raw_faq["faqs"]
            ],
        }
        faq_json_ld = managed_faq_json(managed_faq, canonical)

    return {
        "anthem_seo_override": override,
        "managed_faq": managed_faq,
        "faq_json_ld": faq_json_ld,
    }
