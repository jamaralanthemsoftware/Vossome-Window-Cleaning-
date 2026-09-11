import secrets
import re
import urllib.parse
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .google_integration import (
    GoogleClient, GoogleIntegrationError, authorization_url, create_pkce,
    decrypt_refresh_token, encrypt_refresh_token, exchange_code,
)
from .models import GoogleIntegration, SiteSettings


GA4_KEY_EVENTS = (
    "text_cta_clicked",
    "booking_cta_clicked",
    "booking_completed",
    "contact_form_submitted",
)


def superuser_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                f"/{settings.ADMIN_URL}login/",
            )
        if not settings.ENABLE_GOOGLE_SERVICES_INTEGRATION:
            return HttpResponse("Google services integration is disabled.", status=404)
        if not request.user.is_superuser:
            return HttpResponseForbidden("Superuser access required.")
        return view(request, *args, **kwargs)
    return never_cache(wrapped)


def integration():
    return GoogleIntegration.objects.first()


@superuser_required
@require_GET
def dashboard(request):
    record = integration()
    accounts = []
    selected_account = None
    error = ""
    if record and record.refresh_token_encrypted:
        try:
            accounts = GoogleClient(decrypt_refresh_token(record.refresh_token_encrypted)).accounts()
            selected_name = (
                f"accounts/{record.analytics_account_id}"
                if record.analytics_account_id
                else ""
            )
            selected_account = next(
                (
                    account
                    for account in accounts
                    if account.get("name") == selected_name
                ),
                None,
            )
        except GoogleIntegrationError as exc:
            error = str(exc)
    ga4_configured = bool(
        record
        and record.analytics_account_id
        and record.analytics_property_id
        and record.analytics_data_stream_id
        and record.analytics_measurement_id
    )
    return render(
        request,
        "admin/google/dashboard.html",
        {
            "integration": record,
            "accounts": accounts,
            "selected_account": selected_account,
            "ga4_configured": ga4_configured,
            "ga4_key_events": GA4_KEY_EVENTS,
            "error": error,
        },
    )


@superuser_required
@require_GET
def connect(request):
    state = secrets.token_urlsafe(32)
    verifier, challenge = create_pkce()
    request.session["google_integration_oauth"] = {"state": state, "verifier": verifier}
    return redirect(authorization_url(state, challenge))


@superuser_required
@require_GET
def callback(request):
    saved = request.session.get("google_integration_oauth") or {}
    state = request.GET.get("state", "")
    if not saved or not state or not secrets.compare_digest(state, saved.get("state", "")):
        return HttpResponse("Invalid OAuth state.", status=400)
    request.session.pop("google_integration_oauth", None)
    if request.GET.get("error"):
        return HttpResponse("Google authorization was not completed.", status=400)
    try:
        token = exchange_code(request.GET["code"], saved["verifier"])
        access = token.get("access_token")
        if not access:
            raise GoogleIntegrationError("Google did not return an access token.")
        # Userinfo is intentionally read only to establish the connected identity.
        from .google_integration import _request
        profile = _request("https://openidconnect.googleapis.com/v1/userinfo",
                           headers={"Authorization": f"Bearer {access}"})
        email = profile.get("email", "")
        subject = str(profile.get("sub", "")).strip()
        if not email or not subject or profile.get("email_verified") is not True:
            raise GoogleIntegrationError("Google did not return a verified authenticated identity.")
        if email.casefold() not in settings.GOOGLE_INTEGRATION_ALLOWED_EMAILS:
            raise GoogleIntegrationError("This Google identity is not approved for services integration.")
        record = integration() or GoogleIntegration()
        if record.google_subject and record.google_subject != subject:
            raise GoogleIntegrationError("This Google identity does not match the existing connection.")
        refresh_token = token.get("refresh_token")
        if not refresh_token and (not record.refresh_token_encrypted or record.google_subject != subject):
            raise GoogleIntegrationError("Google did not return a refresh token for this identity.")
        with transaction.atomic():
            record.google_subject = subject
            record.connected_email = email
            record.email_verified = True
            if refresh_token:
                record.refresh_token_encrypted = encrypt_refresh_token(refresh_token)
            record.save()
    except (KeyError, GoogleIntegrationError) as exc:
        return HttpResponse(str(exc), status=400)
    return redirect("google-integration-dashboard")


@superuser_required
@require_GET
def provisioning_callback(request, state):
    saved = request.session.get("google_account_provisioning") or {}
    if not saved or not secrets.compare_digest(state, saved.get("state", "")):
        return HttpResponse("Invalid provisioning state.", status=400)
    if timezone.now().timestamp() - saved.get("created_at", 0) > 600:
        request.session.pop("google_account_provisioning", None)
        return HttpResponse("Provisioning state expired.", status=400)
    request.session.pop("google_account_provisioning", None)
    account_id = request.GET.get("accountId", "").strip()
    record = integration()
    if not record or not account_id.isdigit():
        return HttpResponse("Google did not return a valid account.", status=400)
    try:
        valid = {
            item.get("name", "").rsplit("/", 1)[-1]
            for item in GoogleClient(
                decrypt_refresh_token(record.refresh_token_encrypted)
            ).accounts()
        }
    except GoogleIntegrationError as exc:
        return HttpResponse(str(exc), status=502)
    if account_id not in valid:
        return HttpResponse("Google did not return the provisioned account.", status=400)
    record.analytics_account_id = account_id
    record.save(update_fields=["analytics_account_id", "updated_at"])
    messages.success(
        request,
        "Returned from Google Analytics account creation. "
        "Select the new account below to finish GA4 setup.",
    )
    return redirect("google-integration-dashboard")


@superuser_required
@require_POST
def disconnect(request):
    record = integration()
    if record:
        measurement_id = record.analytics_measurement_id
        verification_token = record.gsc_verification_token
        try:
            GoogleClient(decrypt_refresh_token(record.refresh_token_encrypted)).revoke()
        except GoogleIntegrationError:
            pass
        record.delete()
        site = SiteSettings.objects.first()
        if site:
            changed = []
            if measurement_id and site.analytics_measurement_id == measurement_id:
                site.analytics_measurement_id = ""
                changed.append("analytics_measurement_id")
            if verification_token and site.search_console_verification_token == verification_token:
                site.search_console_verification_token = ""
                changed.append("search_console_verification_token")
            if changed:
                site.save(update_fields=changed + ["updated_at"])
    messages.success(request, "Google services disconnected.")
    return redirect("google-integration-dashboard")


def _client():
    record = get_object_or_404(GoogleIntegration, refresh_token_encrypted__gt="")
    return record, GoogleClient(decrypt_refresh_token(record.refresh_token_encrypted))


@superuser_required
@require_POST
def ga4_create_account(request):
    _record, client = _client()
    provisioning_state = secrets.token_urlsafe(32)
    callback_uri = (
        f"{settings.SITE_URL}/integrations/google/provisioning-callback/"
        f"{urllib.parse.quote(provisioning_state, safe='')}/"
    )
    try:
        result = client.provision_account_ticket(
            callback_uri,
        )
        ticket = result.get("accountTicketId", "").strip()
        if not ticket:
            raise GoogleIntegrationError(
                "Google did not return an Analytics account ticket."
            )
    except GoogleIntegrationError as exc:
        return HttpResponse(str(exc), status=502)

    request.session["google_account_provisioning"] = {
        "state": provisioning_state,
        "ticket": ticket,
        "created_at": timezone.now().timestamp(),
    }
    safe_ticket = urllib.parse.quote(ticket, safe="")
    return redirect(
        "https://analytics.google.com/analytics/web/"
        f"?provisioningSignup=false"
        f"#/termsofservice/{safe_ticket}"
    )


@superuser_required
@require_POST
def ga4_setup(request):
    record, client = _client()
    account = request.POST.get("account_id", "").strip()
    if not account:
        return HttpResponse("Select an Analytics account.", status=400)
    account_id = account.rsplit("/", 1)[-1]
    if record.analytics_account_id and account_id != record.analytics_account_id:
        return HttpResponse(
            "The Analytics account is locked for this connection. "
            "Disconnect Google Services before choosing a different account.",
            status=409,
        )
    try:
        accounts = client.accounts()
        valid_accounts = {item.get("name") for item in accounts}
        if account not in valid_accounts:
            return HttpResponse("Select a valid Analytics account.", status=400)
        record.analytics_account_id = account_id
        record.save(update_fields=["analytics_account_id", "updated_at"])

        if not record.analytics_property_id:
            existing_properties = client.properties(account_id)
            result = None
            for item in existing_properties:
                if item.get("displayName") != "Vossome Window Cleaning":
                    continue
                property_name = item.get("name", "")
                if not property_name.startswith("properties/"):
                    continue
                property_id = property_name.split("/")[-1]
                if any(
                    stream.get("type") == "WEB_DATA_STREAM"
                    and stream.get("webStreamData", {}).get("defaultUri") == settings.SITE_URL
                    for stream in client.streams(property_id)
                ):
                    result = item
                    break
            if result is None:
                result = client.property(account_id)
            if not result.get("name", "").startswith("properties/"):
                raise GoogleIntegrationError("Google did not return a property ID.")
            record.analytics_property_id = result.get("name", "").split("/")[-1]
            record.save(
                update_fields=["analytics_property_id", "updated_at"]
            )

        if not record.analytics_data_stream_id:
            existing_streams = client.streams(
                record.analytics_property_id
            )
            result = next(
                (
                    item
                    for item in existing_streams
                    if item.get("type") == "WEB_DATA_STREAM"
                    and item.get("webStreamData", {}).get("defaultUri")
                    == settings.SITE_URL
                ),
                None,
            )
            if result is None:
                result = client.stream(record.analytics_property_id)
            if (
                not result.get("name", "").startswith("properties/")
                or not result.get("webStreamData", {}).get("measurementId")
            ):
                raise GoogleIntegrationError("Google did not return stream identifiers.")
            record.analytics_data_stream_id = result.get("name", "").split("/")[-1]
            record.analytics_measurement_id = result.get("webStreamData", {}).get("measurementId", "")
            record.full_clean()
            record.save(
                update_fields=[
                    "analytics_data_stream_id",
                    "analytics_measurement_id",
                    "updated_at",
                ]
            )

        existing = client.key_events(record.analytics_property_id)
        for event in GA4_KEY_EVENTS:
            if event not in existing:
                client.key_event(record.analytics_property_id, event)
        site = SiteSettings.objects.first() or SiteSettings()
        site.analytics_measurement_id = record.analytics_measurement_id
        site.full_clean()
        site.save(update_fields=["analytics_measurement_id", "updated_at"])
    except GoogleIntegrationError as exc:
        return HttpResponse(str(exc), status=502)
    messages.success(request, "Google Analytics 4 is configured.")
    return redirect("google-integration-dashboard")


@superuser_required
@require_POST
def gsc_token(request):
    record, client = _client()
    try:
        returned_token = client.verification_token().get("token", "").strip()
        meta_match = re.search(
            r"""content=["']([A-Za-z0-9_-]+)["']""",
            returned_token,
        )
        token = meta_match.group(1) if meta_match else returned_token
        if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            raise GoogleIntegrationError(
                "Google did not return a valid HTML verification token."
            )
        record.gsc_verification_token = token
        record.save(update_fields=["gsc_verification_token", "updated_at"])
        site = SiteSettings.objects.first() or SiteSettings()
        site.search_console_verification_token = token
        site.full_clean()
        if site.pk:
            site.save(
                update_fields=[
                    "search_console_verification_token",
                    "updated_at",
                ]
            )
        else:
            site.save()
    except GoogleIntegrationError as exc:
        return HttpResponse(str(exc), status=502)
    messages.success(
        request,
        "The Search Console verification tag is installed in the website head.",
    )
    return redirect("google-integration-dashboard")


@superuser_required
@require_POST
def gsc_verify(request):
    record, client = _client()
    if not record.gsc_verification_token:
        return HttpResponse(
            "Request and install the HTML verification tag first.",
            status=400,
        )
    try:
        if not record.gsc_verified_at:
            try:
                client.verify()
            except GoogleIntegrationError as exc:
                if "already" not in str(exc).lower():
                    raise
            record.gsc_verified_at = timezone.now()
        if not record.gsc_property_added_at:
            try:
                client.add_property()
            except GoogleIntegrationError as exc:
                if "already" not in str(exc).lower():
                    raise
            record.gsc_property_added_at = timezone.now()
        if not record.gsc_sitemap_submitted_at:
            try:
                client.submit_sitemap()
            except GoogleIntegrationError as exc:
                if "already" not in str(exc).lower():
                    raise
            record.gsc_sitemap_submitted_at = timezone.now()
        record.save(update_fields=["gsc_verified_at", "gsc_property_added_at",
                                   "gsc_sitemap_submitted_at", "updated_at"])
    except GoogleIntegrationError as exc:
        return HttpResponse(str(exc), status=502)
    messages.success(
        request,
        "Search Console is verified and the sitemap was submitted.",
    )
    return redirect("google-integration-dashboard")