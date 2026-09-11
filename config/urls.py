from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from core.admin_auth import admin_sso_login, emergency_admin_login
from core.sitemaps import PageSitemap, ServiceSitemap

sitemaps = {
    "pages": PageSitemap,
    "services": ServiceSitemap,
}

urlpatterns = [
    path(f"{settings.ADMIN_URL}login/", admin_sso_login, name="admin-sso-login"),
    path(
        settings.ADMIN_LOCAL_LOGIN_URL,
        emergency_admin_login,
        name="emergency-admin-login",
    ),
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("integrations/google/", include("core.google_urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("core.urls")),
]

if settings.SERVE_LOCAL_MEDIA and not settings.MEDIA_URL.startswith("http"):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
