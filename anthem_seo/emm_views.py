"""CSRF-exempt EMM connector endpoints for Anthem CRM."""

from __future__ import annotations

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .emm import (
    EmmSignatureError,
    poll_once,
    publish_blog_post,
    resolve_emm_config,
    verify_inbound_site_request,
)

logger = logging.getLogger(__name__)


def _no_store(response: JsonResponse) -> JsonResponse:
    response["Cache-Control"] = "no-store"
    return response


@csrf_exempt
@require_http_methods(["GET", "POST"])
def emm_wake(request):
    """Handle Anthem CRM wake pings and trigger an immediate signed connector poll."""
    if request.method == "GET":
        cfg = resolve_emm_config()
        return _no_store(
            JsonResponse(
                {
                    "ok": True,
                    "status": "ok",
                    "site_id": cfg["site_id"],
                    "configured": bool(cfg["site_id"] and cfg["secret"]),
                },
                status=200,
            )
        )

    try:
        cfg = verify_inbound_site_request(request)
    except EmmSignatureError as exc:
        return _no_store(JsonResponse({"ok": False, "error": str(exc)}, status=exc.status_code))

    try:
        poll_result = poll_once(
            site_id=cfg["site_id"],
            endpoint=cfg["endpoint"],
            secret=cfg["secret"],
            site_url=cfg["home_url"],
        )
        commands_processed = int(poll_result.get("commands_processed") or 0)
        if commands_processed > 0:
            # Deliver last_result immediately back to Anthem.
            poll_once(
                site_id=cfg["site_id"],
                endpoint=cfg["endpoint"],
                secret=cfg["secret"],
                site_url=cfg["home_url"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("EMM wake poll failed: %s", exc)
        return _no_store(
            JsonResponse(
                {
                    "ok": False,
                    "status": "error",
                    "site_id": cfg["site_id"],
                    "error": str(exc),
                },
                status=502,
            )
        )

    return _no_store(
        JsonResponse(
            {
                "ok": True,
                "status": "ok",
                "site_id": cfg["site_id"],
                "revision": poll_result.get("revision", "0"),
                "commands_processed": commands_processed,
            },
            status=200,
        )
    )


@csrf_exempt
@require_http_methods(["POST"])
def emm_publish(request):
    """Receive a signed blog publish payload from Anthem CRM (``POST /emm/api/v1/publish/``)."""
    try:
        verify_inbound_site_request(request)
    except EmmSignatureError as exc:
        return _no_store(JsonResponse({"status": "error", "error": str(exc)}, status=exc.status_code))

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON payload must be an object.")
    except (UnicodeDecodeError, ValueError) as exc:
        return _no_store(JsonResponse({"status": "error", "error": f"Invalid JSON: {exc}"}, status=400))

    try:
        result = publish_blog_post(payload)
    except ValueError as exc:
        return _no_store(JsonResponse({"status": "error", "error": str(exc)}, status=400))
    except Exception as exc:  # noqa: BLE001
        logger.exception("EMM publish failed")
        return _no_store(JsonResponse({"status": "error", "error": str(exc)}, status=500))

    return _no_store(JsonResponse(result, status=200))
