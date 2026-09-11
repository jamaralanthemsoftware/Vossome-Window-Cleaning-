"""Small Google OAuth and REST client with explicit transport error handling."""
import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class GoogleIntegrationError(Exception):
    pass


def _fernet():
    key = settings.GOOGLE_INTEGRATION_ENCRYPTION_KEY
    if not key:
        raise GoogleIntegrationError("GOOGLE_INTEGRATION_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise GoogleIntegrationError("GOOGLE_INTEGRATION_ENCRYPTION_KEY is invalid.") from None


def encrypt_refresh_token(token):
    if not token:
        raise GoogleIntegrationError("Google did not return a refresh token.")
    return _fernet().encrypt(token.encode()).decode()


def decrypt_refresh_token(value):
    if not value:
        raise GoogleIntegrationError("No Google refresh token is stored.")
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeDecodeError):
        raise GoogleIntegrationError("Stored Google refresh token cannot be decrypted.") from None


SCOPES = (
    "openid email https://www.googleapis.com/auth/analytics.edit "
    "https://www.googleapis.com/auth/webmasters https://www.googleapis.com/auth/siteverification"
)


def create_pkce():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(state, challenge):
    query = urllib.parse.urlencode({
        "client_id": settings.GOOGLE_INTEGRATIONS_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_INTEGRATION_CALLBACK_URI,
        "response_type": "code", "scope": SCOPES, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true",
    })
    return "https://accounts.google.com/o/oauth2/v2/auth?" + query


def _request(url, data=None, headers=None, method=None):
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method=method or ("POST" if data else "GET")
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read()
    except HTTPError as exc:
        raise GoogleIntegrationError(f"Google request failed (HTTP {exc.code}).") from None
    except URLError:
        raise GoogleIntegrationError("Google request failed (network error).") from None
    if not payload:
        return {}
    try:
        decoded = json.loads(payload)
    except (ValueError, TypeError):
        raise GoogleIntegrationError("Google returned an invalid response.") from None
    if not isinstance(decoded, dict):
        raise GoogleIntegrationError("Google returned an unexpected response.")
    if "error" in decoded:
        raise GoogleIntegrationError("Google API request was rejected.")
    return decoded


def exchange_code(code, verifier):
    payload = urllib.parse.urlencode({
        "code": code, "client_id": settings.GOOGLE_INTEGRATIONS_CLIENT_ID,
        "client_secret": settings.GOOGLE_INTEGRATIONS_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_INTEGRATION_CALLBACK_URI,
        "grant_type": "authorization_code", "code_verifier": verifier,
    }).encode()
    return _request("https://oauth2.googleapis.com/token", payload,
                    {"Content-Type": "application/x-www-form-urlencoded"})


class GoogleClient:
    def __init__(self, refresh_token):
        self.refresh_token = refresh_token

    def _access_token(self):
        result = _request(
            "https://oauth2.googleapis.com/token",
            urllib.parse.urlencode({
                "client_id": settings.GOOGLE_INTEGRATIONS_CLIENT_ID,
                "client_secret": settings.GOOGLE_INTEGRATIONS_CLIENT_SECRET,
                "refresh_token": self.refresh_token, "grant_type": "refresh_token",
            }).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = result.get("access_token")
        if not token:
            raise GoogleIntegrationError("Google did not provide an access token.")
        return token

    def revoke(self):
        """Revoke the refresh token; callers may continue cleanup on failure."""
        _request(
            "https://oauth2.googleapis.com/revoke",
            urllib.parse.urlencode({"token": self.refresh_token}).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )

    def request(self, method, url, body=None):
        data = json.dumps(body).encode() if body is not None else None
        return _request(url, data, {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
        }, method)

    def accounts(self):
        return self._paged("https://analyticsadmin.googleapis.com/v1beta/accounts", "accounts")

    def _paged(self, url, key):
        results = []
        page_token = ""
        while True:
            separator = "&" if "?" in url else "?"
            payload = self.request("GET", url + (separator + urllib.parse.urlencode({"pageToken": page_token}) if page_token else ""))
            results.extend(payload.get(key, []))
            page_token = payload.get("nextPageToken", "")
            if not page_token:
                return results

    def provision_account_ticket(
        self,
        redirect_uri,
        display_name="Vossome Window Cleaning",
    ):
        return self.request(
            "POST",
            "https://analyticsadmin.googleapis.com/v1beta/accounts:provisionAccountTicket",
            {
                "account": {
                    "displayName": display_name,
                    "regionCode": "US",
                },
                "redirectUri": redirect_uri,
            },
        )

    def property(self, account, name="Vossome Window Cleaning"):
        return self.request("POST", f"https://analyticsadmin.googleapis.com/v1beta/properties", {
            "parent": f"accounts/{account}", "displayName": name,
            "timeZone": "America/Detroit", "currencyCode": "USD",
        })

    def properties(self, account):
        query = urllib.parse.urlencode(
            {"filter": f"parent:accounts/{account}"}
        )
        return self._paged(f"https://analyticsadmin.googleapis.com/v1beta/properties?{query}", "properties")

    def stream(self, property_id):
        return self.request("POST", f"https://analyticsadmin.googleapis.com/v1beta/properties/{property_id}/dataStreams", {
            "type": "WEB_DATA_STREAM",
            "displayName": "Vossome Window Cleaning website",
            "webStreamData": {"defaultUri": settings.SITE_URL},
        })

    def streams(self, property_id):
        return self._paged(
            "https://analyticsadmin.googleapis.com/v1beta/"
            f"properties/{property_id}/dataStreams", "dataStreams"
        )

    def key_event(self, property_id, event_name):
        return self.request("POST", "https://analyticsadmin.googleapis.com/v1beta/properties/"
                            f"{property_id}/keyEvents", {"eventName": event_name})

    def key_events(self, property_id):
        return {
            item.get("eventName")
            for item in self._paged(
                f"https://analyticsadmin.googleapis.com/v1beta/properties/{property_id}/keyEvents",
                "keyEvents",
            )
        }

    def verification_token(self):
        return self.request("POST", "https://www.googleapis.com/siteVerification/v1/token", {
            "site": {"identifier": settings.SITE_URL + "/", "type": "SITE"},
            "verificationMethod": "META",
        })

    def verify(self):
        return self.request("POST", "https://www.googleapis.com/siteVerification/v1/webResource?verificationMethod=META", {
            "site": {"identifier": settings.SITE_URL + "/", "type": "SITE"},
        })

    def add_property(self):
        return self.request("PUT", "https://www.googleapis.com/webmasters/v3/sites/"
                            + urllib.parse.quote(settings.SITE_URL + "/", safe=""), {})

    def submit_sitemap(self):
        url = urllib.parse.quote(settings.SITE_URL + "/", safe="")
        sitemap = urllib.parse.quote(settings.SITE_URL + "/sitemap.xml", safe="")
        return self.request("PUT", f"https://www.googleapis.com/webmasters/v3/sites/{url}/sitemaps/{sitemap}", {})