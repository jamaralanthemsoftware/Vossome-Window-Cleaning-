"""Settings for a temporary client-review site before production integrations exist."""

from .base import *  # noqa: F403

DEBUG = False

# Preview sites deliberately use local administration and database-backed leads.
# Google OAuth, SMTP, Spaces, analytics, and a custom domain are not prerequisites.
ENABLE_GOOGLE_ADMIN_SSO = False
ENABLE_ANTHEM_FORM_DELIVERY = False
ENABLE_RECAPTCHA = False
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
SERVE_LOCAL_MEDIA = not env_bool("USE_SPACES")  # noqa: F405

# Replit and hosted review URLs already terminate HTTPS at their proxy. Unlike
# production, preview mode does not force redirects or HSTS before a domain is ready.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = env_bool("PREVIEW_SECURE_COOKIES", True)  # noqa: F405
CSRF_COOKIE_SECURE = env_bool("PREVIEW_SECURE_COOKIES", True)  # noqa: F405
SECURE_HSTS_SECONDS = 0
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"