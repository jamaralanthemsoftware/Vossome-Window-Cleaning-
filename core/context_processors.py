from django.conf import settings

from .models import Page, SiteSettings


def site_settings(request):
    settings_record = SiteSettings.objects.first() or SiteSettings()
    navigation_pages = Page.objects.filter(
        is_published=True,
        show_in_navigation=True,
    ).exclude(slug__in={"about", "contact", "faq", "services"})
    return {
        "site_settings": settings_record,
        "navigation_pages": navigation_pages,
        "site_url": settings.SITE_URL,
    }
