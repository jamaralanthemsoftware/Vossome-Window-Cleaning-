import json
import socket
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.anthem import deliver_lead_to_anthem
from core.models import AnthemIntegration, Lead


VALID_WEBHOOK = (
    "https://live.anthemcrm.com/api/v1/organization/396/"
    "gravity-forms-webhook/"
)


class AnthemDeliveryTests(TestCase):
    def setUp(self):
        AnthemIntegration.objects.update_or_create(
            singleton_key="default",
            defaults={"webhook_url": VALID_WEBHOOK, "is_enabled": True},
        )

    def make_lead(self):
        return Lead.objects.create(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            phone="3145550123",
            service_interest=Lead.ServiceInterest.WINDOW_CLEANING,
            message="Please contact me about an estimate.",
            consent_to_contact=True,
        )

    def mocked_connection(self, connection_class, *, status, body):
        connection = connection_class.return_value
        connection.sock = connection
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = body
        return connection

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_201_success_true_confirms_exact_payload(self, connection_class):
        lead = self.make_lead()
        connection = self.mocked_connection(
            connection_class,
            status=201,
            body=b'{"success":true,"message":"Prospect added!","results":{"id":987}}',
        )

        self.assertTrue(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.CONFIRMED,
        )
        self.assertEqual(lead.anthem_http_status, 201)
        self.assertEqual(lead.anthem_record_identifier, "987")
        _, path = connection.request.call_args.args[:2]
        payload = json.loads(connection.request.call_args.kwargs["body"])
        self.assertEqual(path, "/api/v1/organization/396/gravity-forms-webhook/")
        self.assertEqual(
            payload,
            {
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane@example.com",
                "cell_phone": "3145550123",
                "notes": (
                    "Service interested in: Window Cleaning\n"
                    "Message: Please contact me about an estimate."
                ),
            },
        )

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_200_success_false_needs_review(self, connection_class):
        lead = self.make_lead()
        self.mocked_connection(
            connection_class,
            status=200,
            body=b'{"success":false,"message":"Rejected","results":{}}',
        )

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
        )
        self.assertEqual(lead.anthem_http_status, 200)

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_http_error_needs_review_without_retry(self, connection_class):
        lead = self.make_lead()
        connection = self.mocked_connection(
            connection_class,
            status=500,
            body=b'{"success":false}',
        )

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
        )
        self.assertEqual(connection.request.call_count, 1)
        self.assertFalse(deliver_lead_to_anthem(lead.pk))
        self.assertEqual(connection.request.call_count, 1)

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_timeout_is_uncertain_and_not_retried(self, connection_class):
        lead = self.make_lead()
        connection = connection_class.return_value
        connection.connect.side_effect = socket.timeout()

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
        )
        self.assertIn("check CRM", lead.anthem_error_summary)
        self.assertFalse(deliver_lead_to_anthem(lead.pk))
        self.assertEqual(connection.connect.call_count, 1)

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_invalid_json_needs_review(self, connection_class):
        lead = self.make_lead()
        self.mocked_connection(
            connection_class,
            status=201,
            body=b"<html>unexpected</html>",
        )

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
        )
        self.assertEqual(lead.anthem_error_summary, "Anthem returned a non-JSON response.")

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_unexpected_json_shape_needs_review(self, connection_class):
        lead = self.make_lead()
        self.mocked_connection(
            connection_class,
            status=201,
            body=b'["not", "an", "object"]',
        )

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.NEEDS_REVIEW,
        )
        self.assertEqual(
            lead.anthem_error_summary,
            "Anthem returned an unexpected JSON response.",
        )

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_missing_configuration_is_visible_to_admin(self, connection_class):
        lead = self.make_lead()
        AnthemIntegration.objects.all().delete()

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.CONFIGURATION_ERROR,
        )
        self.assertIn("not configured", lead.anthem_error_summary)
        connection_class.assert_not_called()

    @override_settings(
        ENABLE_ANTHEM_FORM_DELIVERY=True,
    )
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_wrong_host_is_rejected_before_contact_data_is_sent(self, connection_class):
        lead = self.make_lead()
        AnthemIntegration.objects.update(
            webhook_url=(
                "https://evil.example/api/v1/organization/396/"
                "gravity-forms-webhook/"
            )
        )

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.CONFIGURATION_ERROR,
        )
        connection_class.assert_not_called()

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=True)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_admin_disabled_integration_does_not_send(self, connection_class):
        lead = self.make_lead()
        AnthemIntegration.objects.update(is_enabled=False)

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.CONFIGURATION_ERROR,
        )
        self.assertIn("disabled in Django admin", lead.anthem_error_summary)
        connection_class.assert_not_called()

    @override_settings(ENABLE_ANTHEM_FORM_DELIVERY=False)
    @patch("core.anthem.http.client.HTTPSConnection")
    def test_deployment_kill_switch_overrides_admin_setting(self, connection_class):
        lead = self.make_lead()

        self.assertFalse(deliver_lead_to_anthem(lead.pk))

        lead.refresh_from_db()
        self.assertEqual(
            lead.anthem_delivery_status,
            Lead.AnthemDeliveryStatus.CONFIGURATION_ERROR,
        )
        self.assertIn("not enabled", lead.anthem_error_summary)
        connection_class.assert_not_called()