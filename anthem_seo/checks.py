from django.core.checks import Error, register

from .contract import BundleError, load_bundle


@register()
def anthem_seo_bundle_check(app_configs, **kwargs):
    try:
        load_bundle()
    except BundleError as exc:
        return [Error(f"Invalid Anthem SEO bundle: {exc}", id="anthem_seo.E001")]
    return []
