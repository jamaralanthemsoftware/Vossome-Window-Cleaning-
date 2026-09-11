from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import FAQ, Page, Service
from core.models import Lead


class PublicSiteStructureTests(TestCase):
    def test_public_pages_position_vossome_as_the_company_clients_hire(self):
        home_response = self.client.get(reverse("home"))
        services_response = self.client.get(reverse("services"))
        about_response = self.client.get(reverse("about"))

        self.assertContains(home_response, "We’re in the Happy Client Business")
        self.assertContains(home_response, "The Vossome standard")
        self.assertContains(services_response, "A consistent experience, every visit.")
        self.assertContains(about_response, "Customers should know what to expect from Vossome")
        self.assertNotContains(home_response, "Owners, not subcontractors")
        self.assertNotContains(services_response, "Call or text Matt")

    def test_public_pages_do_not_reference_generated_postcard_or_service_scenes(self):
        for name in ["home", "services"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertNotContains(response, "postcard-")

        for slug in [
            "pressure-washing",
            "gutter-cleaning",
            "concrete-patio-cleaning",
        ]:
            service = Service.objects.get(slug=slug)
            response = self.client.get(service.get_absolute_url())
            self.assertNotContains(response, f"service-{slug}.jpg")

    def test_each_service_uses_its_matching_stock_hero(self):
        expected_images = {
            "window-cleaning": (
                "service-window-cleaning.webp",
                "Clean exterior windows on a well-kept residential home",
            ),
            "pressure-washing": (
                "service-pressure-washing.webp",
                "Professional pressure washing on a residential driveway",
            ),
            "gutter-cleaning": (
                "service-gutter-cleaning.webp",
                "Autumn leaves clogging a residential roof gutter",
            ),
            "concrete-patio-cleaning": (
                "service-concrete-patio-cleaning.webp",
                "Concrete patio being pressure washed in warm evening light",
            ),
        }

        for slug, (image_name, alt_text) in expected_images.items():
            with self.subTest(slug=slug):
                service = Service.objects.get(slug=slug)
                response = self.client.get(service.get_absolute_url())
                image_stem, image_extension = image_name.rsplit(".", 1)
                self.assertContains(response, f"/static/images/{image_stem}.")
                self.assertContains(response, f".{image_extension}")
                self.assertContains(response, f'alt="{alt_text}"')

    @override_settings(ALLOWED_HOSTS=["vossome-window-cleaning.example"])
    def test_internal_platform_health_probe_bypasses_host_validation_only_for_healthz(self):
        health_response = self.client.get(
            reverse("healthz"),
            HTTP_HOST="100.127.38.14",
        )
        public_response = self.client.get(
            reverse("home"),
            HTTP_HOST="100.127.38.14",
        )

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json(), {"status": "ok"})
        self.assertEqual(public_response.status_code, 400)

    def test_required_pages_render_without_content_records(self):
        for name in ["home", "about", "services", "faq", "contact"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_contact_page_embeds_the_vossome_google_map_accessibly(self):
        response = self.client.get(reverse("contact"))

        self.assertContains(response, "https://www.google.com/maps/embed?pb=")
        self.assertContains(
            response,
            'title="Map showing Vossome Window Cleaning in St. Charles, Missouri"',
        )
        self.assertContains(response, 'width="100%" height="100%"')
        self.assertContains(response, 'loading="lazy"')
        self.assertContains(response, 'referrerpolicy="strict-origin-when-cross-origin"')

    def test_contact_page_marks_up_the_business_postal_address(self):
        response = self.client.get(reverse("contact"))

        self.assertContains(response, 'itemtype="https://schema.org/LocalBusiness"')
        self.assertContains(response, 'itemtype="https://schema.org/PostalAddress"')
        self.assertContains(response, '<span itemprop="streetAddress">2745 McClay Rd</span>')
        self.assertContains(response, '<span itemprop="addressLocality">St Charles</span>')
        self.assertContains(response, '<span itemprop="addressRegion">MO</span>')
        self.assertContains(response, '<span itemprop="postalCode">63303</span>')

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Vossome Website <info@vossomewindowcleaning.com>",
        LEAD_NOTIFICATION_EMAIL="vossomewindowcleaning@gmail.com",
    )
    def test_contact_submission_sends_postmark_ready_lead_notification(self):
        response = self.client.post(
            reverse("contact"),
            {
                "first_name": "Happy",
                "last_name": "Client",
                "email": "client@example.com",
                "phone": "(314) 555-0100",
                "service_interest": "window-cleaning",
                "message": "Please send me a quote.",
                "consent_to_contact": "on",
            },
        )

        self.assertRedirects(response, reverse("contact"))
        self.assertEqual(len(mail.outbox), 1)
        notification = mail.outbox[0]
        self.assertEqual(
            notification.to,
            ["vossomewindowcleaning@gmail.com"],
        )
        self.assertEqual(notification.reply_to, ["client@example.com"])
        self.assertIn("Happy Client", notification.subject)
        self.assertIn("(314) 555-0100", notification.body)
        self.assertIn("Service: Window Cleaning", notification.body)
        self.assertIn("Please send me a quote.", notification.body)

    @override_settings(LEAD_NOTIFICATION_EMAIL="vossomewindowcleaning@gmail.com")
    @patch("core.views.EmailMessage.send", side_effect=RuntimeError("Postmark unavailable"))
    def test_email_delivery_failure_does_not_lose_the_lead(self, send):
        response = self.client.post(
            reverse("contact"),
            {
                "first_name": "Saved",
                "last_name": "Client",
                "email": "saved@example.com",
                "service_interest": "gutter-cleaning",
                "message": "Keep this lead even if email fails.",
                "consent_to_contact": "on",
            },
        )

        self.assertRedirects(response, reverse("contact"))
        self.assertTrue(Lead.objects.filter(email="saved@example.com").exists())
        send.assert_called_once()

    def test_contact_form_requires_separate_names_and_service_interest(self):
        response = self.client.get(reverse("contact"))

        self.assertContains(response, 'name="first_name"')
        self.assertContains(response, 'name="last_name"')
        self.assertContains(response, 'name="service_interest"')
        for label in [
            "Window Cleaning",
            "Pressure Washing",
            "Gutter Cleaning",
            "Concrete Patio Cleaning",
        ]:
            self.assertContains(response, label)

        invalid = self.client.post(
            reverse("contact"),
            {
                "first_name": "Missing",
                "last_name": "Service",
                "email": "missing-service@example.com",
                "message": "No service selected.",
                "consent_to_contact": "on",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(
            Lead.objects.filter(email="missing-service@example.com").exists()
        )

    def test_header_and_footer_include_required_navigation(self):
        response = self.client.get(reverse("home"))

        for label in ["Home", "About us", "Services", "FAQ", "Get a free quote"]:
            with self.subTest(label=label):
                self.assertContains(response, label)

    def test_header_quote_link_is_the_only_contact_form_link_on_conversion_pages(self):
        pages = [self.client.get(reverse("home")), self.client.get(reverse("services"))]
        pages.extend(
            self.client.get(Service.objects.get(slug=slug).get_absolute_url())
            for slug in [
                "window-cleaning",
                "pressure-washing",
                "gutter-cleaning",
                "concrete-patio-cleaning",
            ]
        )

        for response in pages:
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertEqual(response.content.count(b'href="/contact/"'), 1)

    def test_home_and_service_heroes_offer_call_and_text_actions(self):
        pages = [self.client.get(reverse("home"))]
        pages.extend(
            self.client.get(Service.objects.get(slug=slug).get_absolute_url())
            for slug in [
                "window-cleaning",
                "pressure-washing",
                "gutter-cleaning",
                "concrete-patio-cleaning",
            ]
        )

        for response in pages:
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertContains(response, 'href="tel:+13147751080">Call us</a>')
                self.assertContains(response, 'href="sms:+13147751080">Text us</a>')

    def test_about_page_uses_published_about_record(self):
        Page.objects.create(
            title="Our story",
            slug="about",
            body="Client-managed about content.",
            is_published=True,
        )

        response = self.client.get(reverse("about"))

        self.assertContains(response, "Our story")
        self.assertContains(response, "Client-managed about content.")

    def test_service_listing_links_to_each_published_service(self):
        service = Service.objects.create(
            title="Example service",
            slug="example-service",
            summary="A useful service.",
            is_published=True,
        )

        response = self.client.get(reverse("services"))

        self.assertContains(response, service.title)
        self.assertContains(response, service.get_absolute_url())
        self.assertEqual(self.client.get(service.get_absolute_url()).status_code, 200)

    def test_service_detail_renders_structured_content_without_exposed_tags(self):
        service = Service.objects.create(
            title="Structured service",
            slug="structured-service",
            summary="A useful service.",
            body="<h2>Helpful heading</h2><p>Readable service information.</p>",
            is_published=True,
        )

        response = self.client.get(service.get_absolute_url())

        self.assertContains(response, "<h2>Helpful heading</h2>", html=True)
        self.assertContains(response, "<p>Readable service information.</p>", html=True)
        self.assertNotContains(response, "&lt;p&gt;")

    def test_faq_page_shows_only_published_items(self):
        FAQ.objects.create(
            question="Published question?",
            answer="<p>Published answer.</p>",
            is_published=True,
        )
        FAQ.objects.create(
            question="Draft question?",
            answer="Draft answer.",
            is_published=False,
        )

        response = self.client.get(reverse("faq"))

        self.assertContains(response, "Published question?")
        self.assertNotContains(response, "Draft question?")
        self.assertNotContains(response, "&lt;p&gt;")

    def test_page_generates_search_and_open_graph_metadata_from_content(self):
        page = Page.objects.create(
            title="Planning for a confident retirement",
            slug="retirement-planning",
            summary="Understand the steps involved in building a durable financial plan.",
            body="Detailed planning guidance.",
            is_published=False,
        )

        self.assertEqual(page.meta_title, page.title)
        self.assertEqual(page.open_graph_title, page.title)
        self.assertIn("durable financial plan", page.meta_description)
        self.assertIn("durable financial plan", page.open_graph_description)

    def test_published_content_page_requires_approximately_750_words(self):
        page = Page(
            title="Short page",
            slug="short-page",
            body="Too short.",
            is_published=True,
        )

        with self.assertRaises(ValidationError):
            page.full_clean()

        page.body = " ".join(["useful"] * 750)
        page.full_clean()

    def test_detail_page_assigns_article_open_graph_elements(self):
        page = Page.objects.create(
            title="Detailed guidance",
            slug="detailed-guidance",
            summary="A focused description for search and sharing.",
            body=" ".join(["guidance"] * 750),
            open_graph_image=SimpleUploadedFile("sharing.jpg", b"image-bytes"),
            is_published=True,
        )

        response = self.client.get(page.get_absolute_url())

        self.assertContains(response, 'property="og:type" content="article"')
        self.assertContains(response, f'property="og:title" content="{page.open_graph_title}"')
        self.assertContains(response, 'property="og:image" content="http://testserver/')

    def test_content_page_renders_structured_html_without_exposed_tags(self):
        page = Page.objects.create(
            title="Structured guidance",
            slug="structured-guidance",
            body="<h2>Useful heading</h2><p>Readable page information.</p>",
            is_published=True,
        )

        response = self.client.get(page.get_absolute_url())

        self.assertContains(response, "<h2>Useful heading</h2>", html=True)
        self.assertContains(response, "<p>Readable page information.</p>", html=True)
        self.assertNotContains(response, "&lt;p&gt;")