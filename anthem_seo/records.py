"""Adapter mapping djangocms-master-template models and built-in routes to SEO records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.models import BlogPost, FAQ, Page, Service, SiteSettings


STATIC_ROUTES = (
    ("page-home", "/", "Home", "Welcome to Vossome Window Cleaning."),
    ("page-about", "/about/", "About us", "Learn more about Vossome Window Cleaning in St. Charles, MO."),
    ("page-services", "/services/", "Services", "Explore window cleaning, pressure washing, and gutter cleaning services."),
    ("page-commercial", "/commercial-window-cleaning/", "Commercial Window Cleaning", "Brighter View Commercial Window Cleaning in St. Charles and Greater St. Louis."),
    ("page-faq", "/faq/", "FAQ", "Frequently asked questions."),
    ("page-contact", "/contact/", "Contact us", "Get a straightforward quote from Vossome Window Cleaning."),
    ("page-blog", "/blog/", "Blog", "Homeowner guides, pricing breakdowns, and exterior maintenance tips."),
)


@dataclass
class SeoRecord:
    pk: str
    reverse_id: str
    cms_path: str
    title: str
    page_title: str
    meta_description: str
    body_html: str = ""
    is_home: bool = False
    is_public: bool = True
    changed_date: Optional[datetime] = None
    og_image_url: str = ""
    has_cms_faq: bool = False
    model_kind: str = "static"
    instance: object = None


def _site_name() -> str:
    try:
        record = SiteSettings.objects.first()
        if record and record.site_name:
            return record.site_name
    except Exception:
        pass
    return "Client Website"


def _blog_reverse_id(post: BlogPost) -> str:
    guid = (getattr(post, "source_guid", "") or "").strip()
    if guid.startswith("anthem:"):
        return guid[len("anthem:"):]
    return f"blog-{post.slug}"


def _record_from_page(page: Page, *, cms_path: Optional[str] = None, reverse_id: Optional[str] = None) -> SeoRecord:
    rev_id = reverse_id or f"page-{page.slug}"
    path = cms_path or ("/about/" if page.slug == "about" else f"/{page.slug}/")
    og_img = ""
    try:
        if page.open_graph_image:
            og_img = page.open_graph_image.url
    except Exception:
        og_img = ""
    return SeoRecord(
        pk=f"page:{page.pk}",
        reverse_id=rev_id,
        cms_path=path,
        title=page.title,
        page_title=page.seo_title,
        meta_description=page.seo_description,
        body_html=page.body or "",
        is_home=False,
        is_public=bool(page.is_published),
        changed_date=getattr(page, "updated_at", None),
        og_image_url=og_img,
        has_cms_faq=False,
        model_kind="page",
        instance=page,
    )


def _record_from_service(service: Service) -> SeoRecord:
    og_img = ""
    try:
        if service.open_graph_image:
            og_img = service.open_graph_image.url
    except Exception:
        og_img = ""
    return SeoRecord(
        pk=f"service:{service.pk}",
        reverse_id=f"svc-{service.slug}",
        cms_path=f"/services/{service.slug}/",
        title=service.title,
        page_title=service.seo_title,
        meta_description=service.seo_description,
        body_html=service.body or "",
        is_home=False,
        is_public=bool(service.is_published),
        changed_date=getattr(service, "updated_at", None),
        og_image_url=og_img,
        has_cms_faq=False,
        model_kind="service",
        instance=service,
    )


def _record_from_blog_post(post: BlogPost) -> SeoRecord:
    og_img = ""
    try:
        if getattr(post, "featured_image", None):
            og_img = post.featured_image.url
        elif getattr(post, "open_graph_image", None):
            og_img = post.open_graph_image.url
        elif getattr(post, "hero_image_static", None):
            og_img = f"/static/{post.hero_image_static.lstrip('/')}"
    except Exception:
        og_img = ""
    return SeoRecord(
        pk=f"blog:{post.pk}",
        reverse_id=_blog_reverse_id(post),
        cms_path=f"/blog/{post.slug}/",
        title=post.title,
        page_title=post.seo_title,
        meta_description=post.seo_description,
        body_html=post.body or "",
        is_home=False,
        is_public=bool(post.is_published),
        changed_date=getattr(post, "original_modified_at", None) or getattr(post, "updated_at", None),
        og_image_url=og_img,
        has_cms_faq=False,
        model_kind="blog",
        instance=post,
    )


def _static_record(reverse_id: str, cms_path: str, title: str, default_desc: str, *, site_name: Optional[str] = None) -> SeoRecord:
    resolved_site_name = site_name or _site_name()
    if reverse_id == "page-about":
        about_page = Page.objects.filter(slug="about").first()
        if about_page is not None:
            rec = _record_from_page(about_page, cms_path="/about/", reverse_id="page-about")
            # /about/ renders with fallback content even when the Page record is draft
            rec.is_public = True
            return rec
    has_faq = False
    if reverse_id == "page-faq":
        try:
            has_faq = FAQ.objects.filter(is_published=True).exists()
        except Exception:
            has_faq = False
    page_title = resolved_site_name if reverse_id == "page-home" else f"{title} | {resolved_site_name}"
    return SeoRecord(
        pk=f"static:{reverse_id}",
        reverse_id=reverse_id,
        cms_path=cms_path,
        title=title,
        page_title=page_title,
        meta_description=default_desc,
        body_html="",
        is_home=(reverse_id == "page-home"),
        is_public=True,
        changed_date=None,
        og_image_url="",
        has_cms_faq=has_faq,
        model_kind="static",
        instance=None,
    )


def all_cms_records() -> list[SeoRecord]:
    site_name = _site_name()
    records = [
        _static_record(rev_id, path, title, desc, site_name=site_name)
        for rev_id, path, title, desc in STATIC_ROUTES
    ]
    seen_reverse_ids = {rec.reverse_id for rec in records}

    for page in Page.objects.exclude(slug="about").order_by("slug"):
        rec = _record_from_page(page)
        if rec.reverse_id not in seen_reverse_ids:
            records.append(rec)
            seen_reverse_ids.add(rec.reverse_id)

    for service in Service.objects.order_by("slug"):
        rec = _record_from_service(service)
        if rec.reverse_id not in seen_reverse_ids:
            records.append(rec)
            seen_reverse_ids.add(rec.reverse_id)

    for post in BlogPost.objects.order_by("slug"):
        rec = _record_from_blog_post(post)
        if rec.reverse_id not in seen_reverse_ids:
            records.append(rec)
            seen_reverse_ids.add(rec.reverse_id)

    return records


def record_for_reverse_id(reverse_id: str) -> Optional[SeoRecord]:
    if not reverse_id:
        return None
    for rev_id, path, title, desc in STATIC_ROUTES:
        if reverse_id == rev_id:
            return _static_record(rev_id, path, title, desc)
    if reverse_id.startswith("page-"):
        slug = reverse_id[len("page-"):]
        page = Page.objects.filter(slug=slug).first()
        return _record_from_page(page) if page else None
    if reverse_id.startswith("svc-"):
        slug = reverse_id[len("svc-"):]
        service = Service.objects.filter(slug=slug).first()
        return _record_from_service(service) if service else None
    post = BlogPost.objects.filter(source_guid=f"anthem:{reverse_id}").first()
    if post is None and reverse_id.startswith("blog-"):
        slug = reverse_id[len("blog-"):]
        post = BlogPost.objects.filter(slug=slug).first()
    if post is not None:
        return _record_from_blog_post(post)
    return None
