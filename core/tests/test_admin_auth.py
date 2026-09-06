from types import SimpleNamespace
from unittest.mock import Mock

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.auth import AdminSocialAccountAdapter


class AdminAuthenticationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="approved-admin",
            email="approved@example.com",
            password="a-long-development-password",
            is_staff=True,
        )

    @override_settings(ENABLE_GOOGLE_ADMIN_SSO=False)
    def test_local_admin_login_is_available_when_sso_is_disabled(self):
        response = self.client.get(reverse("admin:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")

    @override_settings(ENABLE_GOOGLE_ADMIN_SSO=True)
    def test_normal_admin_login_redirects_to_google_when_sso_is_enabled(self):
        response = self.client.get(reverse("admin:login"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("google_login"), response.url)
        self.assertIn("process=login", response.url)

    def test_emergency_login_is_separate_from_normal_admin_login(self):
        response = self.client.get(reverse("emergency-admin-login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")

    def test_short_local_password_is_rejected_by_validator(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            validate_password("too-short", user=self.staff_user)

    @override_settings(ADMIN_GOOGLE_ALLOWED_EMAILS={"approved@example.com"})
    def test_google_login_connects_only_to_existing_staff_user(self):
        social_login = SimpleNamespace(
            user=SimpleNamespace(email="Approved@Example.com"),
            is_existing=False,
            connect=Mock(),
        )

        AdminSocialAccountAdapter().pre_social_login(None, social_login)

        social_login.connect.assert_called_once_with(None, self.staff_user)

    @override_settings(ADMIN_GOOGLE_ALLOWED_EMAILS={"approved@example.com"})
    def test_unapproved_google_email_is_denied(self):
        social_login = SimpleNamespace(
            user=SimpleNamespace(email="intruder@example.com"),
            is_existing=False,
            connect=Mock(),
        )

        with self.assertRaises(ImmediateHttpResponse):
            AdminSocialAccountAdapter().pre_social_login(None, social_login)

        social_login.connect.assert_not_called()

    @override_settings(ADMIN_GOOGLE_ALLOWED_EMAILS={"visitor@example.com"})
    def test_non_staff_user_cannot_gain_admin_access_through_google(self):
        get_user_model().objects.create_user(
            username="visitor",
            email="visitor@example.com",
            password="a-long-development-password",
            is_staff=False,
        )
        social_login = SimpleNamespace(
            user=SimpleNamespace(email="visitor@example.com"),
            is_existing=False,
            connect=Mock(),
        )

        with self.assertRaises(ImmediateHttpResponse):
            AdminSocialAccountAdapter().pre_social_login(None, social_login)

        social_login.connect.assert_not_called()