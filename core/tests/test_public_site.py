from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import FAQ, Page, Service


class PublicSiteStructureTests(TestCase):
    def test_required_pages_render_without_content_records(self):
        for name in ["home", "about", "services", "faq", "contact"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_header_and_footer_include_required_navigation(self):
        response = self.client.get(reverse("home"))

        for label in ["Home", "About us", "Services", "FAQ", "Contact us"]:
            with self.subTest(label=label):
                self.assertContains(response, label)

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