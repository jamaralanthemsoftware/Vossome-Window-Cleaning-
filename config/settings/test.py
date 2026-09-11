from .development import *  # noqa: F403

ENABLE_ANTHEM_FORM_DELIVERY = False
ANTHEM_FORM_WEBHOOK_URL = ""

STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}