from django.test import TestCase, override_settings
from django.urls import reverse

from config.csp import CONTENT_SECURITY_POLICY


@override_settings(CONTENT_SECURITY_POLICY=CONTENT_SECURITY_POLICY)
class ContentSecurityPolicyTests(TestCase):
    def test_public_contact_and_admin_responses_enforce_the_policy(self):
        for route_name in ("home", "contact", "admin:login"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(
                    response["Content-Security-Policy"],
                    CONTENT_SECURITY_POLICY,
                )

    def test_policy_does_not_enable_inline_or_evaluated_scripts(self):
        response = self.client.get(reverse("contact"))
        policy = response["Content-Security-Policy"]

        self.assertNotIn("'unsafe-eval'", policy)
        script_policy = next(
            directive
            for directive in policy.split("; ")
            if directive.startswith("script-src ")
        )
        self.assertNotIn("'unsafe-inline'", script_policy)

    def test_policy_limits_google_features_to_required_paths(self):
        response = self.client.get(reverse("contact"))
        policy = response["Content-Security-Policy"]

        self.assertIn("https://www.googletagmanager.com/gtag/js", policy)
        self.assertIn("https://www.google.com/recaptcha/", policy)
        self.assertIn("https://www.google.com/maps/", policy)
        self.assertIn("https://www.google-analytics.com/g/collect", policy)
        self.assertNotIn("https://www.google.com ", policy)
        self.assertNotIn("https://www.googletagmanager.com ", policy)