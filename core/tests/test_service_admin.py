from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Service


class ServiceAdminGuidanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="service-editor",
            email="editor@example.com",
            password="a-long-development-password",
        )
        self.client.force_login(self.user)

    def test_window_cleaning_body_shows_editing_guidance(self):
        service = Service.objects.get(slug="window-cleaning")
        response = self.client.get(reverse("admin:core_service_change", args=[service.pk]))

        self.assertContains(response, "edit the words inside each heading")
        self.assertContains(response, "data-window-chapter")
        self.assertContains(response, "move the whole heading and its content")
        self.assertContains(response, "window-pricing")
        self.assertContains(response, "Copy and prices remain editable")
        self.assertContains(response, 'name="body"')

    def test_other_services_do_not_show_window_specific_guidance(self):
        service = Service.objects.get(slug="pressure-washing")
        response = self.client.get(reverse("admin:core_service_change", args=[service.pk]))

        self.assertNotContains(response, "Window Cleaning sections:")
        self.assertContains(response, 'name="body"')