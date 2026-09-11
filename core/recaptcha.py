import http.client
import json
import math
import socket
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings


VERIFY_HOST = "www.google.com"
VERIFY_PATH = "/recaptcha/api/siteverify"
EXPECTED_ACTION = "contact_form"
CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 7
MAX_RESPONSE_BYTES = 32_768


@dataclass(frozen=True)
class RecaptchaConfig:
    site_key: str
    minimum_score: float
    allowed_hostnames: frozenset[str]


def get_contact_recaptcha_config():
    if not settings.ENABLE_RECAPTCHA:
        return None
    from .models import RecaptchaIntegration

    integration = RecaptchaIntegration.objects.filter(
        singleton_key="default",
        is_enabled=True,
    ).first()
    if not integration:
        return None
    return RecaptchaConfig(
        site_key=integration.site_key,
        minimum_score=float(integration.minimum_score),
        allowed_hostnames=frozenset(integration.normalized_hostnames),
    )


def verify_contact_recaptcha(token, config=None):
    if not settings.ENABLE_RECAPTCHA:
        return True
    config = config or get_contact_recaptcha_config()
    if config is None:
        return True
    if not token or not settings.RECAPTCHA_SECRET_KEY:
        return False

    body = urlencode(
        {
            "secret": settings.RECAPTCHA_SECRET_KEY,
            "response": token,
        }
    ).encode("utf-8")
    connection = http.client.HTTPSConnection(
        VERIFY_HOST,
        443,
        timeout=CONNECT_TIMEOUT_SECONDS,
    )
    try:
        connection.connect()
        connection.sock.settimeout(READ_TIMEOUT_SECONDS)
        connection.request(
            "POST",
            VERIFY_PATH,
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        response = connection.getresponse()
        response_body = response.read(MAX_RESPONSE_BYTES + 1)
        if (
            response.status != 200
            or len(response_body) > MAX_RESPONSE_BYTES
        ):
            return False
        result = json.loads(response_body)
        if not isinstance(result, dict):
            return False
        try:
            score = float(result.get("score", -1))
        except (TypeError, ValueError):
            return False
        if not math.isfinite(score) or not 0 <= score <= 1:
            return False
        return (
            result.get("success") is True
            and result.get("action") == EXPECTED_ACTION
            and score >= config.minimum_score
            and str(result.get("hostname", "")).lower()
            in config.allowed_hostnames
        )
    except (
        OSError,
        TimeoutError,
        socket.timeout,
        http.client.HTTPException,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return False
    finally:
        connection.close()