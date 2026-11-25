from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_blogs_after_migrate(sender, **kwargs):
    if getattr(sender, "name", None) not in {"core", "anthem_seo"}:
        return
    try:
        from .blogs import sync_anthem_blogs
        from .contract import load_bundle

        bundle = load_bundle()
        if not bundle.get("posts"):
            return
        sync_anthem_blogs(bundle=bundle)
    except Exception:
        return


class AnthemSeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "anthem_seo"
    verbose_name = "Anthem SEO"

    def ready(self):
        from . import checks  # noqa: F401

        post_migrate.connect(
            _sync_blogs_after_migrate,
            dispatch_uid="anthem_seo.sync_blogs_after_migrate",
        )
