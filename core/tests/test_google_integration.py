import base64
import hashlib
from unittest.mock import Mock, patch
import urllib.parse

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.google_integration import (
    GoogleClient,
    GoogleIntegrationError,
    decrypt_refresh_token,
    encrypt_refresh_token,
)
from core.models import AnthemIntegration, GoogleIntegration, SiteSettings


KEY = Fernet.generate_key().decode()
GOOGLE_SETTINGS = {
    "GOOGLE_INTEGRATION_ENCRYPTION_KEY": KEY,
    "GOOGLE_INTEGRATIONS_CLIENT_ID": "client-id",
    "GOOGLE_INTEGRATIONS_CLIENT_SECRET": "client-secret",
    "ENABLE_GOOGLE_SERVICES_INTEGRATION": True,
    "GOOGLE_INTEGRATION_ALLOWED_EMAILS": {"owner@example.com", "admin@example.com"},
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
}


@override_settings(**GOOGLE_SETTINGS)
class GoogleIntegrationTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="google-admin", email="admin@example.com", password="a-long-password-123"
        )
        self.staff = get_user_model().objects.create_user(
            username="staff", email="staff@example.com", password="a-long-password-123", is_staff=True
        )
        self.client.force_login(self.superuser)

    def test_access_control_and_no_cache(self):
        self.client.logout()
        response = self.client.get(reverse("google-integration-dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"/{settings.ADMIN_URL}login/?next=/integrations/google/",
        )
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("google-integration-dashboard")).status_code, 403
        )
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("google-integration-connect"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("no-cache", response["Cache-Control"])
        self.assertIn("code_challenge=", response.url)

    def test_authorization_uses_s256_pkce_and_separate_integration_client(self):
        response = self.client.get(reverse("google-integration-connect"))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(response.url).query)
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        saved = self.client.session["google_integration_oauth"]
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(saved["verifier"].encode()).digest()
        ).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], [expected])

    def test_staff_cannot_see_google_integration_admin_module(self):
        from core.admin import GoogleIntegrationAdmin
        from django.contrib import admin

        request = RequestFactory().get("/")
        request.user = self.staff
        self.assertFalse(
            GoogleIntegrationAdmin(GoogleIntegration, admin.site).has_module_permission(request)
        )

    def test_anthem_integration_admin_module_is_superuser_only(self):
        from django.contrib import admin

        from core.admin import AnthemIntegrationAdmin

        request = RequestFactory().get("/")
        request.user = self.staff
        integration_admin = AnthemIntegrationAdmin(AnthemIntegration, admin.site)
        self.assertFalse(integration_admin.has_module_permission(request))

        request.user = self.superuser
        self.assertTrue(integration_admin.has_module_permission(request))

    def test_google_integration_admin_link_opens_setup_dashboard(self):
        response = self.client.get(
            reverse("admin:core_googleintegration_changelist")
        )
        self.assertRedirects(
            response,
            reverse("google-integration-dashboard"),
            fetch_redirect_response=False,
        )

    def test_fernet_requires_valid_key_and_does_not_leak(self):
        encrypted = encrypt_refresh_token("refresh-secret")
        self.assertEqual(decrypt_refresh_token(encrypted), "refresh-secret")
        self.assertNotIn("refresh-secret", encrypted)
        with override_settings(GOOGLE_INTEGRATION_ENCRYPTION_KEY="not-a-fernet-key"):
            with self.assertRaises(GoogleIntegrationError):
                encrypt_refresh_token("refresh-secret")

    @patch("core.google_views.exchange_code")
    @patch("core.google_integration._request")
    def test_callback_validates_state_and_encrypts_token(self, userinfo, exchange):
        session = self.client.session
        session["google_integration_oauth"] = {"state": "state", "verifier": "verifier"}
        session.save()
        exchange.return_value = {"access_token": "access", "refresh_token": "refresh-secret"}
        userinfo.return_value = {"email": "owner@example.com", "sub": "sub-1", "email_verified": True}
        response = self.client.get(reverse("google-integration-callback"), {"state": "state", "code": "code"})
        self.assertRedirects(response, reverse("google-integration-dashboard"))
        record = GoogleIntegration.objects.get()
        self.assertEqual(decrypt_refresh_token(record.refresh_token_encrypted), "refresh-secret")
        self.assertNotIn("refresh-secret", response.url)
        self.assertNotIn("google_integration_oauth", self.client.session)

    @patch("core.google_views.exchange_code", return_value={"access_token": "access"})
    @patch("core.google_integration._request", return_value={"email": "owner@example.com", "sub": "sub-1", "email_verified": True})
    def test_reconnect_rejects_unbound_identity_without_refresh_token(self, _userinfo, _exchange):
        record = GoogleIntegration.objects.create(
            connected_email="old@example.com", refresh_token_encrypted=encrypt_refresh_token("old")
        )
        session = self.client.session
        session["google_integration_oauth"] = {"state": "state", "verifier": "verifier"}
        session.save()
        response = self.client.get(reverse("google-integration-callback"), {"state": "state", "code": "code"})
        self.assertEqual(response.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(decrypt_refresh_token(record.refresh_token_encrypted), "old")

    def test_first_callback_without_refresh_token_fails(self):
        session = self.client.session
        session["google_integration_oauth"] = {"state": "state", "verifier": "verifier"}
        session.save()
        with patch("core.google_views.exchange_code", return_value={"access_token": "access"}), patch(
            "core.google_integration._request", return_value={"email": "owner@example.com", "sub": "sub-1", "email_verified": True}
        ):
            response = self.client.get(
                reverse("google-integration-callback"), {"state": "state", "code": "code"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GoogleIntegration.objects.exists())

    def test_callback_rejects_unverified_or_unapproved_identity(self):
        session = self.client.session
        session["google_integration_oauth"] = {"state": "state", "verifier": "verifier"}
        session.save()
        with patch("core.google_views.exchange_code", return_value={"access_token": "access"}), patch(
            "core.google_integration._request",
            return_value={"email": "owner@example.com", "sub": "s", "email_verified": False},
        ):
            response = self.client.get(reverse("google-integration-callback"), {"state": "state", "code": "code"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GoogleIntegration.objects.exists())

    def test_callback_rejects_different_subject_without_changing_record(self):
        record = GoogleIntegration.objects.create(
            google_subject="original", connected_email="owner@example.com",
            email_verified=True, refresh_token_encrypted=encrypt_refresh_token("old"),
        )
        session = self.client.session
        session["google_integration_oauth"] = {"state": "state", "verifier": "verifier"}
        session.save()
        with patch("core.google_views.exchange_code", return_value={"access_token": "access"}), patch(
            "core.google_integration._request",
            return_value={"email": "owner@example.com", "sub": "different", "email_verified": True},
        ):
            response = self.client.get(reverse("google-integration-callback"), {"state": "state", "code": "code"})
        self.assertEqual(response.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.google_subject, "original")
        self.assertEqual(decrypt_refresh_token(record.refresh_token_encrypted), "old")

    @patch("core.google_views.GoogleClient")
    def test_create_analytics_account_ticket_and_return_from_terms(
        self,
        client_class,
    ):
        GoogleIntegration.objects.create(
            connected_email="owner@example.com",
            refresh_token_encrypted=encrypt_refresh_token("refresh"),
        )
        client_class.return_value.provision_account_ticket.return_value = {
            "accountTicketId": "ticket/with spaces"
        }
        client_class.return_value.accounts.return_value = [{"name": "accounts/123"}]

        response = self.client.post(
            reverse("google-integration-ga4-create-account")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "https://analytics.google.com/analytics/web/?provisioningSignup=false",
            response.url,
        )
        self.assertIn("#/termsofservice/ticket%2Fwith%20spaces", response.url)
        provisioning = self.client.session["google_account_provisioning"]
        self.assertTrue(provisioning["state"])
        self.assertIn("created_at", provisioning)
        client_class.return_value.provision_account_ticket.assert_called_once_with(
            f"{settings.SITE_URL}/integrations/google/provisioning-callback/"
            f"{urllib.parse.quote(provisioning['state'], safe='')}/"
        )

        response = self.client.get(
            reverse(
                "google-integration-provisioning-callback",
                kwargs={"state": provisioning["state"]},
            ),
            {"accountId": "123", "accountTicketId": "ticket/with spaces"},
        )
        self.assertRedirects(
            response,
            reverse("google-integration-dashboard"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(
            "google_account_provisioning",
            self.client.session,
        )

    @patch("core.google_views.GoogleClient")
    def test_create_analytics_account_requires_a_ticket(self, client_class):
        GoogleIntegration.objects.create(
            connected_email="owner@example.com",
            refresh_token_encrypted=encrypt_refresh_token("refresh"),
        )
        client_class.return_value.provision_account_ticket.return_value = {}

        response = self.client.post(
            reverse("google-integration-ga4-create-account")
        )

        self.assertEqual(response.status_code, 502)
        self.assertContains(
            response,
            "did not return an Analytics account ticket",
            status_code=502,
        )

    @patch("core.google_views.GoogleClient")
    def test_provisioning_rejects_inaccessible_account_and_reused_state(self, client_class):
        GoogleIntegration.objects.create(refresh_token_encrypted=encrypt_refresh_token("refresh"))
        client_class.return_value.provision_account_ticket.return_value = {"accountTicketId": "ticket"}
        client_class.return_value.accounts.return_value = []
        self.client.post(reverse("google-integration-ga4-create-account"))
        state = self.client.session["google_account_provisioning"]["state"]
        response = self.client.get(
            reverse("google-integration-provisioning-callback", kwargs={"state": state}),
            {"accountId": "999"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("google_account_provisioning", self.client.session)
        self.assertEqual(
            self.client.get(
                reverse("google-integration-provisioning-callback", kwargs={"state": state}),
                {"accountId": "999"},
            ).status_code,
            400,
        )

    def test_disabled_services_integration_is_not_accessible(self):
        with override_settings(ENABLE_GOOGLE_SERVICES_INTEGRATION=False):
            response = self.client.get(reverse("google-integration-dashboard"))
        self.assertEqual(response.status_code, 404)

    @patch("core.google_views.GoogleClient")
    def test_ga_setup_validates_account_identifiers_and_persists_idempotently(self, client_class):
        record = GoogleIntegration.objects.create(refresh_token_encrypted=encrypt_refresh_token("refresh"))
        api = client_class.return_value
        api.accounts.return_value = [{"name": "accounts/123", "displayName": "Main"}]
        api.properties.return_value = []
        api.property.return_value = {"name": "properties/456"}
        api.streams.return_value = []
        api.stream.return_value = {
            "name": "properties/456/dataStreams/789",
            "type": "WEB_DATA_STREAM",
            "webStreamData": {"defaultUri": settings.SITE_URL, "measurementId": "G-ABC123"},
        }
        api.key_events.return_value = {
            "text_cta_clicked",
            "booking_cta_clicked",
            "booking_completed",
            "contact_form_submitted",
        }
        url = reverse("google-integration-ga4-setup")
        self.assertEqual(self.client.post(url, {"account_id": "accounts/evil"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"account_id": "accounts/123"}).status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.analytics_measurement_id, "G-ABC123")
        self.assertEqual(SiteSettings.objects.first().analytics_measurement_id, "G-ABC123")
        self.assertEqual(api.property.call_count, 1)
        self.assertEqual(api.stream.call_count, 1)
        self.client.post(url, {"account_id": "accounts/123"})
        self.assertEqual(api.property.call_count, 1)
        self.assertEqual(api.key_event.call_count, 0)

    @patch("core.google_views.GoogleClient")
    def test_configured_dashboard_locks_account_and_shows_measurement_id(
        self, client_class
    ):
        GoogleIntegration.objects.create(
            connected_email="owner@example.com",
            refresh_token_encrypted=encrypt_refresh_token("refresh"),
            analytics_account_id="407479029",
            analytics_property_id="456",
            analytics_data_stream_id="789",
            analytics_measurement_id="G-ABC123",
        )
        client_class.return_value.accounts.return_value = [
            {
                "name": "accounts/407479029",
                "displayName": "Vossome Window Cleaning",
            },
            {"name": "accounts/61675729", "displayName": "Cyber Command"},
        ]

        response = self.client.get(reverse("google-integration-dashboard"))

        self.assertContains(response, "Vossome Window Cleaning")
        self.assertContains(response, "G-ABC123")
        self.assertContains(response, "text_cta_clicked")
        self.assertContains(response, "booking_cta_clicked")
        self.assertContains(response, "booking_completed")
        self.assertContains(response, "contact_form_submitted")
        self.assertContains(response, "The Analytics account is locked")
        self.assertNotContains(response, "<select")
        self.assertNotContains(response, "Set up GA4")
        self.assertNotContains(response, "Create a new Analytics account")

        response = self.client.post(
            reverse("google-integration-ga4-setup"),
            {"account_id": "accounts/61675729"},
        )
        self.assertEqual(response.status_code, 409)
        client_class.return_value.properties.assert_not_called()

    @patch("core.google_views.GoogleClient")
    def test_ga_setup_recovers_existing_property_after_partial_failure(
        self,
        client_class,
    ):
        record = GoogleIntegration.objects.create(
            refresh_token_encrypted=encrypt_refresh_token("refresh")
        )
        api = client_class.return_value
        api.accounts.return_value = [
            {"name": "accounts/123", "displayName": "Main"}
        ]
        api.properties.return_value = [
            {
                "name": "properties/456",
                "displayName": "Vossome Window Cleaning",
            }
        ]
        api.streams.return_value = [{
            "name": "properties/456/dataStreams/789",
            "type": "WEB_DATA_STREAM",
            "webStreamData": {"defaultUri": settings.SITE_URL, "measurementId": "G-ABC123"},
        }]
        api.stream.return_value = {
            "name": "properties/456/dataStreams/789",
            "type": "WEB_DATA_STREAM",
            "webStreamData": {"measurementId": "G-ABC123"},
        }
        api.key_events.return_value = set()

        response = self.client.post(
            reverse("google-integration-ga4-setup"),
            {"account_id": "accounts/123"},
        )

        self.assertEqual(response.status_code, 302)
        api.property.assert_not_called()
        api.stream.assert_not_called()
        record.refresh_from_db()
        self.assertEqual(record.analytics_property_id, "456")
        self.assertEqual(record.analytics_measurement_id, "G-ABC123")
        self.assertEqual(
            [call.args[1] for call in api.key_event.call_args_list],
            [
                "text_cta_clicked",
                "booking_cta_clicked",
                "booking_completed",
                "contact_form_submitted",
            ],
        )

    def test_current_web_stream_type_and_key_event_api_version(self):
        client = GoogleClient("refresh")
        with patch.object(client, "request") as request:
            request.return_value = {
                "name": "properties/456/dataStreams/789"
            }
            client.stream("456")
            body = request.call_args.args[2]
            self.assertEqual(body["type"], "WEB_DATA_STREAM")

            client.key_event("456", "booking_completed")
            self.assertIn("/v1beta/", request.call_args.args[1])

    @patch("core.google_views.GoogleClient")
    def test_ga_setup_rejects_blank_identifiers_and_empty_accounts(self, client_class):
        GoogleIntegration.objects.create(
            connected_email="owner@example.com",
            refresh_token_encrypted=encrypt_refresh_token("refresh"),
        )
        api = client_class.return_value
        api.accounts.return_value = []
        response = self.client.post(
            reverse("google-integration-ga4-setup"), {"account_id": "accounts/123"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            self.client.get(reverse("google-integration-dashboard")), "disabled", count=3
        )

    @patch("core.google_views.GoogleClient")
    def test_search_console_calls_all_operations_and_disconnect_cleans_site(self, client_class):
        record = GoogleIntegration.objects.create(
            refresh_token_encrypted=encrypt_refresh_token("refresh"),
            analytics_measurement_id="G-ABC123",
        )
        site_settings = SiteSettings.objects.first() or SiteSettings()
        site_settings.analytics_measurement_id = "G-ABC123"
        site_settings.save()
        api = client_class.return_value
        api.verification_token.return_value = {
            "token": (
                '<meta name="google-site-verification" '
                'content="verification-token_123" />'
            )
        }
        self.client.post(reverse("google-integration-gsc-token"))
        record.refresh_from_db()
        self.assertEqual(
            record.gsc_verification_token,
            "verification-token_123",
        )
        site = SiteSettings.objects.first()
        self.assertEqual(
            site.search_console_verification_token,
            "verification-token_123",
        )
        homepage = self.client.get(reverse("home"))
        self.assertContains(
            homepage,
            '<meta name="google-site-verification" '
            'content="verification-token_123">',
            html=True,
        )
        self.client.post(reverse("google-integration-gsc-verify"))
        api.verify.assert_called_once()
        api.add_property.assert_called_once()
        api.submit_sitemap.assert_called_once()
        self.client.post(reverse("google-integration-disconnect"))
        self.assertEqual(SiteSettings.objects.first().analytics_measurement_id, "")

    @patch("core.google_views.GoogleClient")
    def test_search_console_requires_installed_verification_tag(
        self, client_class
    ):
        GoogleIntegration.objects.create(
            refresh_token_encrypted=encrypt_refresh_token("refresh"),
        )

        response = self.client.post(
            reverse("google-integration-gsc-verify")
        )

        self.assertEqual(response.status_code, 400)
        client_class.return_value.verify.assert_not_called()

    @patch("core.google_views.GoogleClient")
    def test_disconnect_clears_matching_search_console_token(self, client_class):
        token = "vossome-token"
        record = GoogleIntegration.objects.create(
            refresh_token_encrypted=encrypt_refresh_token("refresh"),
            gsc_verification_token=token,
        )
        site = SiteSettings.objects.first()
        site.search_console_verification_token = token
        site.save()
        self.client.post(reverse("google-integration-disconnect"))
        self.assertEqual(SiteSettings.objects.get().search_console_verification_token, "")
        self.assertFalse(GoogleIntegration.objects.exists())

    def test_search_console_uses_meta_verification_and_url_prefix_property(self):
        client = GoogleClient("refresh")
        with patch.object(client, "request", return_value={}) as request:
            client.verification_token()
            self.assertEqual(
                request.call_args.args[2]["verificationMethod"],
                "META",
            )
            self.assertEqual(
                request.call_args.args[2]["site"],
                {
                    "identifier": settings.SITE_URL + "/",
                    "type": "SITE",
                },
            )

            client.verify()
            self.assertIn(
                "verificationMethod=META",
                request.call_args.args[1],
            )

            client.add_property()
            self.assertIn(
                urllib.parse.quote(settings.SITE_URL + "/", safe=""),
                request.call_args.args[1],
            )
            self.assertNotIn("sc-domain", request.call_args.args[1])

    def test_measurement_validation_and_event_wrapper(self):
        site_settings = SiteSettings.objects.first()
        site_settings.analytics_measurement_id = "G-ABC123"
        site_settings.full_clean()
        site_settings.analytics_measurement_id = "UA-123"
        with self.assertRaises(Exception):
            site_settings.full_clean()
        site_settings.analytics_measurement_id = ""
        site_settings.full_clean()
        with open("static/js/site.js") as javascript:
            source = javascript.read()
        self.assertIn('window.gtag?.("event", name, data || {})', source)

    def test_base_has_conditional_analytics_and_search_console_tags(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "googletagmanager.com/gtag/js")
        self.assertNotContains(response, "google-site-verification")
        site_settings = SiteSettings.objects.first()
        site_settings.analytics_measurement_id = "G-VOSSOME123"
        site_settings.search_console_verification_token = "vossome-token_123"
        site_settings.save()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "googletagmanager.com/gtag/js?id=G-VOSSOME123")
        self.assertContains(
            response,
            '<meta name="google-site-verification" content="vossome-token_123">',
            html=True,
        )

    def test_successful_contact_redirect_signals_form_completion(self):
        self.client.get(reverse("contact"))
        response = self.client.post(
            reverse("contact"),
            {
                "first_name": "Vossome",
                "last_name": "Customer",
                "email": "customer@example.com",
                "phone": "3145550100",
                "service_interest": "window-cleaning",
                "message": "Please quote our windows.",
                "consent_to_contact": "on",
                "submission_token": self.client.session["contact_submission_token"],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("contact"))
        response = self.client.get(reverse("contact"))
        self.assertContains(response, 'data-contact-submitted="true"')
        self.assertContains(response, 'src="/static/js/site.js"')


class GoogleClientTransportTests(TestCase):
    @override_settings(**GOOGLE_SETTINGS)
    @patch("core.google_integration.urllib.request.urlopen")
    def test_empty_successful_response_is_accepted(self, urlopen):
        response = Mock()
        response.read.return_value = b""
        urlopen.return_value.__enter__.return_value = response
        client = GoogleClient("refresh")
        with patch.object(client, "_access_token", return_value="access"):
            self.assertEqual(client.request("PUT", "https://example.test/resource", {}), {})

    @override_settings(**GOOGLE_SETTINGS)
    def test_key_events_are_paginated(self):
        client = GoogleClient("refresh")
        with patch.object(
            client,
            "request",
            side_effect=[
                {"keyEvents": [{"eventName": "text_cta_clicked"}], "nextPageToken": "next"},
                {"keyEvents": [{"eventName": "booking_completed"}]},
            ],
        ) as request:
            self.assertEqual(
                client.key_events("456"),
                {"text_cta_clicked", "booking_completed"},
            )
        self.assertEqual(request.call_count, 2)
