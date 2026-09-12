import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_path(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().strip("/")
    return f"{value}/"


SECRET_KEY = os.getenv("SECRET_KEY", "development-only-key")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")
ADMIN_URL = env_path("ADMIN_URL", "admin")
ADMIN_LOCAL_LOGIN_URL = env_path("ADMIN_LOCAL_LOGIN_URL", "emergency-admin-login")
ENABLE_GOOGLE_ADMIN_SSO = env_bool("ENABLE_GOOGLE_ADMIN_SSO", False)
ADMIN_GOOGLE_ALLOWED_EMAILS = {
    email.casefold() for email in env_list("ADMIN_GOOGLE_ALLOWED_EMAILS")
}
GOOGLE_INTEGRATIONS_CLIENT_ID = os.getenv("GOOGLE_INTEGRATIONS_CLIENT_ID", "")
GOOGLE_INTEGRATIONS_CLIENT_SECRET = os.getenv("GOOGLE_INTEGRATIONS_CLIENT_SECRET", "")
GOOGLE_INTEGRATION_ENCRYPTION_KEY = os.getenv("GOOGLE_INTEGRATION_ENCRYPTION_KEY", "")
ENABLE_GOOGLE_SERVICES_INTEGRATION = env_bool("ENABLE_GOOGLE_SERVICES_INTEGRATION", False)
GOOGLE_INTEGRATION_ALLOWED_EMAILS = {
    email.casefold() for email in env_list("GOOGLE_INTEGRATION_ALLOWED_EMAILS")
}
GOOGLE_INTEGRATION_CALLBACK_URI = f"{SITE_URL}/integrations/google/callback/"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "axes",
    "core",
]

MIDDLEWARE = [
    "core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

CONTENT_SECURITY_POLICY = ""

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_settings",
            ],
        },
    },
]

database_url = os.getenv("DATABASE_URL")
if database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(os.getenv("SQLITE_PATH", BASE_DIR / "db.sqlite3")),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 14},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_ONLY = True
SOCIALACCOUNT_ADAPTER = "core.auth.AdminSocialAccountAdapter"
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "key": "",
        },
    }
}

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_LOCKOUT_TEMPLATE = "security/locked_out.html"

SESSION_COOKIE_AGE = 60 * 60
SESSION_SAVE_EVERY_REQUEST = True

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "America/New_York")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SERVE_LOCAL_MEDIA = env_bool("SERVE_LOCAL_MEDIA", DEBUG)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

if env_bool("USE_SPACES"):
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "nyc3")
    AWS_S3_ENDPOINT_URL = os.getenv(
        "AWS_S3_ENDPOINT_URL",
        f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com",
    )
    AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN") or (
        f"{AWS_STORAGE_BUCKET_NAME}.{AWS_S3_REGION_NAME}.digitaloceanspaces.com"
    )
    AWS_QUERYSTRING_AUTH = False
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"

POSTMARK_SERVER_TOKEN = os.getenv("POSTMARK_SERVER_TOKEN", "")
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    (
        "django.core.mail.backends.smtp.EmailBackend"
        if POSTMARK_SERVER_TOKEN
        else "django.core.mail.backends.console.EmailBackend"
    ),
)
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "Vossome Website <info@vossomewindowcleaning.com>",
)
SERVER_EMAIL = os.getenv("SERVER_EMAIL", "errors@example.com")
EMAIL_HOST = os.getenv(
    "EMAIL_HOST",
    "smtp.postmarkapp.com" if POSTMARK_SERVER_TOKEN else "",
)
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", POSTMARK_SERVER_TOKEN)
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", POSTMARK_SERVER_TOKEN)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
LEAD_NOTIFICATION_EMAIL = os.getenv(
    "LEAD_NOTIFICATION_EMAIL",
    "vossomewindowcleaning@gmail.com",
)
ENABLE_ANTHEM_FORM_DELIVERY = env_bool("ENABLE_ANTHEM_FORM_DELIVERY", False)
TRUST_PROXY_CLIENT_IP_HEADER = env_bool("TRUST_PROXY_CLIENT_IP_HEADER", False)
ENABLE_RECAPTCHA = env_bool("ENABLE_RECAPTCHA", False)
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY", "")
RECAPTCHA_MIN_SCORE = float(os.getenv("RECAPTCHA_MIN_SCORE", "0.5"))
RECAPTCHA_ALLOWED_HOSTNAMES = {
    hostname.strip().lower()
    for hostname in os.getenv(
        "RECAPTCHA_ALLOWED_HOSTNAMES",
        "vossomewindowcleaning.com,www.vossomewindowcleaning.com",
    ).split(",")
    if hostname.strip()
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "loggers": {
        "security.authentication": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "axes.watch_login": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
