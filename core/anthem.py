import http.client
import json
import re
import socket
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Lead


EXPECTED_HOST = "live.anthemcrm.com"
EXPECTED_PATH = re.compile(
    r"^/api/v1/organization/396/gravity-forms-webhook/$"
)
CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 7
MAX_RESPONSE_BYTES = 65_536


class AnthemConfigurationError(ValueError):
    pass


def _validated_destination():
    if not settings.ENABLE_ANTHEM_FORM_DELIVERY:
        raise AnthemConfigurationError("Anthem delivery is not enabled.")
    value = settings.ANTHEM_FORM_WEBHOOK_URL.strip()
    if not value:
        raise AnthemConfigurationError("Anthem webhook is not configured.")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != EXPECTED_HOST
        or parsed.port not in (None, 443)
        or not EXPECTED_PATH.fullmatch(parsed.path)
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise AnthemConfigurationError("Anthem webhook configuration is invalid.")
    return parsed


def _claim_delivery(lead_id):
    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=lead_id)
        if lead.anthem_delivery_status != Lead.AnthemDeliveryStatus.PENDING:
            return None
        lead.anthem_delivery_status = Lead.AnthemDeliveryStatus.ATTEMPTING
        lead.anthem_attempted_at = timezone.now()
        lead.save(
            update_fields=[
                "anthem_delivery_status",
                "anthem_attempted_at",
                "updated_at",
            ]
        )
        return lead


def _record_result(
    lead_id,
    *,
    status,
    http_status=None,
    error_summary="",
    record_identifier="",
):
    Lead.objects.filter(pk=lead_id).update(
        anthem_delivery_status=status,
        anthem_http_status=http_status,
        anthem_error_summary=error_summary[:240],
        anthem_record_identifier=record_identifier[:120],
        updated_at=timezone.now(),
    )


def _extract_record_identifier(response_data):
    results = response_data.get("results")
    if not isinstance(results, dict):
        return ""
    for key in ("id", "prospect_id", "prospectId", "record_id", "recordId"):
        value = results.get(key)
        if isinstance(value, (str, int)):
            return str(value)
    return ""


def deliver_lead_to_anthem(lead_id):
    lead = _claim_delivery(lead_id)
    if lead is None:
        return False

    connection = None
    response_status = None
    try:
        destination = _validated_destination()
        payload = {
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "email": lead.email,
            "cell_phone": lead.phone,
            "notes": (
                f"Service interested in: {lead.get_service_interest_display()}\n"
                f"Message: {lead.message}"
            ),
        }
        encoded_payload = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPSConnection(
            destination.hostname,
            destination.port or 443,
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
        connection.connect()
        connection.sock.settimeout(READ_TIMEOUT_SECONDS)
        connection.request(
            "POST",
            destination.path,
            body=encoded_payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        response = connection.getresponse()
        response_status = response.status
        response_body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise ValueError("Anthem returned an oversized response.")
        try:
            response_data = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            _record_result(
                lead_id,
                status=Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
                http_status=response.status,
                error_summary="Anthem returned a non-JSON response.",
            )
            return False
        if not isinstance(response_data, dict):
            _record_result(
                lead_id,
                status=Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
                http_status=response.status,
                error_summary="Anthem returned an unexpected JSON response.",
            )
            return False
        if 200 <= response.status < 300 and response_data.get("success") is True:
            _record_result(
                lead_id,
                status=Lead.AnthemDeliveryStatus.CONFIRMED,
                http_status=response.status,
                record_identifier=_extract_record_identifier(response_data),
            )
            return True
        _record_result(
            lead_id,
            status=Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
            http_status=response.status,
            error_summary=(
                "Anthem did not confirm delivery "
                f"(HTTP {response.status}, success was not true)."
            ),
        )
        return False
    except AnthemConfigurationError as exc:
        _record_result(
            lead_id,
            status=Lead.AnthemDeliveryStatus.CONFIGURATION_ERROR,
            error_summary=str(exc),
        )
        return False
    except (TimeoutError, socket.timeout):
        _record_result(
            lead_id,
            status=Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
            http_status=response_status,
            error_summary="Anthem delivery timed out; check CRM before resending.",
        )
        return False
    except Exception:
        _record_result(
            lead_id,
            status=Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
            http_status=response_status,
            error_summary="Anthem delivery failed; check CRM before resending.",
        )
        return False
    finally:
        if connection is not None:
            connection.close()