"""Read-only staff status view; this app intentionally has no models."""

from django.contrib import admin
from django.shortcuts import render

from .contract import BundleError, load_bundle
from .records import record_for_reverse_id
from .resolver import resolve_page
from .routing import effective_path


@admin.site.admin_view
def status(request):
    rows = []
    error = None
    bundle = None
    try:
        bundle = load_bundle()
        for binding in bundle["manifest"]["bindings"]:
            record = record_for_reverse_id(binding["cms_ref"]["reverse_id"])
            if record is None:
                continue
            resolved = resolve_page(record, record)
            rows.append({
                "item_id": binding["item_id"],
                "reverse_id": record.reverse_id,
                "raw": resolved["raw"],
                "effective": resolved["effective"],
                "source": resolved["source"],
                "faq_state": resolved["faq_state"],
                "faq_conflict": resolved["faq_conflict"],
                "effective_path": effective_path(record, binding["language"], bundle=bundle),
            })
    except BundleError as exc:
        error = str(exc)
    return render(
        request,
        "admin/anthem_seo/status.html",
        {"rows": rows, "bundle": bundle, "error": error},
    )
