import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

if SECRET_KEY in {"", "development-only-key"}:  # noqa: F405
    raise ImproperlyConfigured("Production requires a strong SECRET_KEY.")

if os.getenv("REQUIRE_POSTGRES", "true").lower() in {"1", "true", "yes", "on"}:
    if not os.getenv("DATABASE_URL"):
        raise ImproperlyConfigured("Production requires DATABASE_URL for PostgreSQL.")

if ALLOWED_HOSTS == ["*"] or not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Set explicit production ALLOWED_HOSTS.")

if ADMIN_URL == "admin/":  # noqa: F405
    raise ImproperlyConfigured("Set a unique ADMIN_URL for production.")

if ADMIN_LOCAL_LOGIN_URL == "emergency-admin-login/":  # noqa: F405
    raise ImproperlyConfigured("Set a unique ADMIN_LOCAL_LOGIN_URL for production.")

if ENABLE_GOOGLE_ADMIN_SSO:  # noqa: F405
    if not os.getenv("GOOGLE_OAUTH_CLIENT_ID") or not os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"):
        raise ImproperlyConfigured(
            "Google admin SSO requires GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
        )
    if not ADMIN_GOOGLE_ALLOWED_EMAILS:  # noqa: F405
        raise ImproperlyConfigured(
            "Google admin SSO requires at least one ADMIN_GOOGLE_ALLOWED_EMAILS value."
        )

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
