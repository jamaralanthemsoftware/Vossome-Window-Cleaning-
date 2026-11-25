from django.conf import settings

from anthem_seo.resolver import resolve_request_overrides
from .models import Page, SiteSettings


def site_settings(request):
    settings_record = SiteSettings.objects.first() or SiteSettings()
    navigation_pages = Page.objects.filter(
        is_published=True,
        show_in_navigation=True,
    ).exclude(slug__in={"about", "blog", "contact", "faq", "services"})
    return {
        "site_settings": settings_record,
        "navigation_pages": navigation_pages,
        "site_url": settings.SITE_URL,
        **resolve_request_overrides(request),
    }
