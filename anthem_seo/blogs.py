"""Idempotent synchronization of Git-managed blog post documents into core.models.BlogPost."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
import html

from django.db import transaction
from django.utils.text import slugify

from .contract import load_bundle


def _parse_published_at(value: str):
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def _render_post_body(post_data: dict) -> str:
    body_html = (post_data.get("body_html") or "").strip()
    featured_image = (post_data.get("featured_image") or "").strip()
    if not featured_image or featured_image in body_html:
        return body_html
    alt_text = (
        post_data.get("featured_image_alt") or post_data.get("title") or ""
    ).strip()
    escaped_src = html.escape(featured_image, quote=True)
    escaped_alt = html.escape(alt_text, quote=True)
    figure = (
        f'<figure class="blog-featured-image">'
        f'<img src="{escaped_src}" alt="{escaped_alt}" loading="lazy">'
        f"</figure>"
    )
    return f"{figure}\n{body_html}"


def sync_anthem_blogs(bundle=None):
    """Upsert all seo/posts/*.json blog documents into core.models.BlogPost."""
    bundle = bundle or load_bundle()
    posts = bundle.get("posts") or {}
    if not posts:
        return {"synced": 0, "items": []}

    from core.models import BlogPost, BlogTopic

    synced_items = []
    for (item_id, language), document in sorted(posts.items()):
        reverse_id = document["cms_ref"]["reverse_id"]
        guid = f"anthem:{reverse_id}"
        post_data = document["post"]
        title = post_data["title"].strip()[:240]
        slug = post_data["slug"].strip()[:240]
        summary = (post_data.get("summary") or "").strip()[:500]
        status = (post_data.get("status") or "publish").strip()
        is_published = status != "draft"
        author_name = (post_data.get("author_name") or "").strip()[:255]
        published_dt = _parse_published_at(
            (post_data.get("published_at") or "").strip()
        )

        page_doc = (bundle.get("pages") or {}).get((item_id, language)) or {}
        seo_overrides = page_doc.get("seo") or {}
        meta_title = ((seo_overrides.get("seo_title") or "").strip() or title)[:70]
        meta_description = (
            (seo_overrides.get("meta_description") or "").strip() or summary
        )[:300]
        canonical_url = (seo_overrides.get("canonical") or "").strip()[:1000]
        rendered_body = _render_post_body(post_data)

        with transaction.atomic():
            blog_post = BlogPost.objects.filter(source_guid=guid).first()
            if blog_post is None:
                blog_post = (
                    BlogPost.objects.filter(slug=slug)
                    .order_by("id")
                    .first()
                )
            defaults = {
                "title": title,
                "slug": slug,
                "summary": summary,
                "body": rendered_body,
                "meta_title": meta_title,
                "meta_description": meta_description,
                "canonical_url": canonical_url,
                "author_name": author_name,
                "is_published": is_published,
                "source_guid": guid,
            }
            if published_dt is not None:
                defaults["original_published_at"] = published_dt
                defaults["original_modified_at"] = published_dt
                defaults["published_at"] = published_dt

            if blog_post is None:
                blog_post = BlogPost.objects.create(**defaults)
            else:
                changed_fields = []
                for field_name, new_val in defaults.items():
                    if getattr(blog_post, field_name, None) != new_val:
                        setattr(blog_post, field_name, new_val)
                        changed_fields.append(field_name)
                if changed_fields:
                    changed_fields.append("updated_at")
                    blog_post.save(update_fields=changed_fields)

            topics = post_data.get("topics")
            if isinstance(topics, list):
                topic_objs = []
                for topic_name in topics:
                    clean_name = (topic_name or "").strip()[:100]
                    topic_slug = slugify(clean_name)[:100]
                    if not clean_name or not topic_slug:
                        continue
                    topic_obj = (
                        BlogTopic.objects.filter(slug=topic_slug).first()
                        or BlogTopic.objects.filter(name=clean_name).first()
                    )
                    if topic_obj is None:
                        topic_obj = BlogTopic.objects.create(
                            name=clean_name,
                            slug=topic_slug,
                        )
                    topic_objs.append(topic_obj)
                blog_post.topics.set(topic_objs)

            synced_items.append(
                {
                    "item_id": item_id,
                    "reverse_id": reverse_id,
                    "slug": (seo_overrides.get("slug") or slug).strip(),
                    "status": "published" if is_published else "draft",
                }
            )

    return {"synced": len(synced_items), "items": synced_items}
