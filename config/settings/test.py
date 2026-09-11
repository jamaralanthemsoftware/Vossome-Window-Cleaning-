from .development import *  # noqa: F403

ENABLE_ANTHEM_FORM_DELIVERY = False

STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}