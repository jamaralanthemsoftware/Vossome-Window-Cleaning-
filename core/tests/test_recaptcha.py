import json
import socket
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from core.recaptcha import verify_contact_recaptcha


RECAPTCHA_SETTINGS = {
    "ENABLE_RECAPTCHA": True,
    "RECAPTCHA_SECRET_KEY": "test-secret",
    "RECAPTCHA_MIN_SCORE": 0.5,
    "RECAPTCHA_ALLOWED_HOSTNAMES": {
        "vossomewindowcleaning.com",
        "www.vossomewindowcleaning.com",
    },
}


@override_settings(**RECAPTCHA_SETTINGS)
class RecaptchaVerificationTests(SimpleTestCase):
    def mocked_response(self, connection_class, payload, status=200):
        connection = connection_class.return_value
        connection.sock = connection
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = json.dumps(payload).encode("utf-8")
        return connection

    @patch("core.recaptcha.http.client.HTTPSConnection")
    def test_valid_contact_action_and_score_are_accepted(self, connection_class):
        connection = self.mocked_response(
            connection_class,
            {
                "success": True,
                "score": 0.9,
                "action": "contact_form",
                "hostname": "vossomewindowcleaning.com",
            },
        )

        self.assertTrue(verify_contact_recaptcha("browser-token"))

        connection.request.assert_called_once()
        self.assertEqual(connection.request.call_args.args[:2], ("POST", "/recaptcha/api/siteverify"))
        request_body = connection.request.call_args.kwargs["body"].decode("utf-8")
        self.assertIn("secret=test-secret", request_body)
        self.assertIn("response=browser-token", request_body)

    @patch("core.recaptcha.http.client.HTTPSConnection")
    def test_low_score_is_rejected(self, connection_class):
        self.mocked_response(
            connection_class,
            {
                "success": True,
                "score": 0.49,
                "action": "contact_form",
                "hostname": "vossomewindowcleaning.com",
            },
        )

        self.assertFalse(verify_contact_recaptcha("browser-token"))

    @patch("core.recaptcha.http.client.HTTPSConnection")
    def test_non_finite_or_out_of_range_score_is_rejected(self, connection_class):
        for score in ["Infinity", -0.1, 1.1]:
            with self.subTest(score=score):
                self.mocked_response(
                    connection_class,
                    {
                        "success": True,
                        "score": score,
                        "action": "contact_form",
                        "hostname": "vossomewindowcleaning.com",
                    },
                )
                self.assertFalse(verify_contact_recaptcha("browser-token"))

    @patch("core.recaptcha.http.client.HTTPSConnection")
    def test_wrong_action_or_hostname_is_rejected(self, connection_class):
        self.mocked_response(
            connection_class,
            {
                "success": True,
                "score": 0.9,
                "action": "login",
                "hostname": "example.com",
            },
        )

        self.assertFalse(verify_contact_recaptcha("browser-token"))

    @patch("core.recaptcha.http.client.HTTPSConnection")
    def test_timeout_fails_closed(self, connection_class):
        connection_class.return_value.connect.side_effect = socket.timeout()

        self.assertFalse(verify_contact_recaptcha("browser-token"))

    @override_settings(ENABLE_RECAPTCHA=False)
    @patch("core.recaptcha.http.client.HTTPSConnection")
    def test_disabled_verification_never_contacts_google(self, connection_class):
        self.assertTrue(verify_contact_recaptcha(""))
        connection_class.assert_not_called()