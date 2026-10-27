from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import BlogPost, FAQ, Lead, Page, RecaptchaIntegration, Service, SiteSettings


def contact_payload(client, **overrides):
    client.get(reverse("contact"))
    payload = {
        "first_name": "Happy",
        "last_name": "Client",
        "service_address": "123 Example Street, St. Charles, MO",
        "preferred_reply_method": "email",
        "email": "client@example.com",
        "phone": "(314) 555-0100",
        "service_interest": "window-cleaning",
        "message": "Please send me a quote.",
        "consent_to_contact": "on",
        "submission_token": client.session["contact_submission_token"],
    }
    payload.update(overrides)
    return payload


class PublicSiteStructureTests(TestCase):
    def test_public_pages_position_vossome_as_the_company_clients_hire(self):
        home_response = self.client.get(reverse("home"))
        services_response = self.client.get(reverse("services"))
        about_response = self.client.get(reverse("about"))

        self.assertContains(home_response, "We’re in the ")
        self.assertContains(home_response, 'class="headline-accent">Happy Client</span>')
        self.assertContains(home_response, 'class="headline-last">Business.</span>')
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

    def test_homepage_includes_brighter_view_commercial_path(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("commercial")}"')
        self.assertContains(response, "Brighter View")
        self.assertContains(response, "brighter-view-logo.")
        self.assertContains(response, ".png")

    def test_commercial_landing_page_renders_with_vossome_standards(self):
        response = self.client.get(reverse("commercial"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Brighter View Commercial Window Cleaning")
        self.assertContains(response, "St. Charles")
        self.assertContains(response, "St. Louis")

    def test_required_pages_render_without_content_records(self):
        for name in ["home", "about", "services", "faq", "contact", "commercial"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_contact_page_prioritizes_text_without_publishing_home_address(self):
        response = self.client.get(reverse("contact"))
        self.assertContains(response, 'href="sms:+13147751080"')
        self.assertContains(response, 'href="#quote-form"')
        self.assertContains(response, 'href="mailto:')
        self.assertContains(response, 'href="tel:+13147751080"')
        self.assertContains(response, "based in St. Charles and serving nearby communities")
        self.assertContains(response, 'href="mailto:vossomewindowcleaning@gmail.com"')
        self.assertContains(response, 'itemtype="https://schema.org/LocalBusiness"')
        self.assertNotContains(response, "streetAddress")
        self.assertNotContains(response, "maps/embed")
        self.assertNotContains(response, "McClay")

    def test_homepage_links_to_google_reviews(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'href="https://share.google/BAmvmaufaIzyEPUQI"')
        self.assertContains(response, "Read our Google reviews")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Vossome Website <info@vossomewindowcleaning.com>",
        LEAD_NOTIFICATION_EMAIL="vossomewindowcleaning@gmail.com",
    )
    def test_contact_submission_sends_postmark_ready_lead_notification(self):
        response = self.client.post(
            reverse("contact"),
            contact_payload(self.client),
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
        self.assertIn("Phone: 3145550100", notification.body)
        self.assertIn("Services: Window Cleaning", notification.body)
        self.assertIn("Please send me a quote.", notification.body)

    @override_settings(LEAD_NOTIFICATION_EMAIL="vossomewindowcleaning@gmail.com")
    @patch("core.views.EmailMessage.send", side_effect=RuntimeError("Postmark unavailable"))
    def test_email_delivery_failure_does_not_lose_the_lead(self, send):
        response = self.client.post(
            reverse("contact"),
            contact_payload(
                self.client,
                first_name="Saved",
                email="saved@example.com",
                service_interest="gutter-cleaning",
                message="Keep this lead even if email fails.",
            ),
        )

        self.assertRedirects(response, reverse("contact"))
        self.assertTrue(Lead.objects.filter(email="saved@example.com").exists())
        send.assert_called_once()

    def test_contact_form_requires_separate_names_and_service_interest(self):
        response = self.client.get(reverse("contact"))

        self.assertContains(response, 'name="submission_token"')
        self.assertContains(
            response,
            f'value="{self.client.session["contact_submission_token"]}"',
        )
        self.assertContains(response, 'name="first_name"')
        self.assertContains(response, 'name="last_name"')
        self.assertContains(response, 'name="services"')
        self.assertContains(response, 'name="preferred_reply_method"')
        for label in [
            "Window cleaning",
            "House washing",
            "Gutter cleaning",
            "Driveway, patio, or walkway cleaning",
            "Deck cleaning (please include material)",
            "A fifteenth-century gargoyle or something else?",
        ]:
            self.assertContains(response, label)

        invalid = self.client.post(
            reverse("contact"),
            contact_payload(
                self.client,
                first_name="Missing",
                last_name="Service",
                email="missing-service@example.com",
                service_interest="",
                message="No service selected.",
            ),
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(
            Lead.objects.filter(email="missing-service@example.com").exists()
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        LEAD_NOTIFICATION_EMAIL="vossomewindowcleaning@gmail.com",
    )
    def test_contact_accepts_bundled_services_and_reply_preference(self):
        response = self.client.post(
            reverse("contact"),
            contact_payload(
                self.client,
                services=["window-cleaning", "pressure-washing", "other"],
                preferred_reply_method="text",
            ),
        )
        self.assertRedirects(response, reverse("contact"))
        lead = Lead.objects.get(email="client@example.com")
        self.assertEqual(lead.selected_services, ["window-cleaning", "pressure-washing", "other"])
        self.assertEqual(lead.service_interest, "window-cleaning")
        self.assertEqual(lead.preferred_reply_method, "text")
        self.assertIn("Window Cleaning, Pressure Washing, Other", mail.outbox[0].body)
        self.assertIn("Preferred reply: Text", mail.outbox[0].body)

    def test_deck_material_optional_and_wood_preserved_for_review(self):
        payload = contact_payload(
            self.client,
            services=["deck-cleaning"],
            service_interest="",
            deck_material="",
        )
        invalid = self.client.post(reverse("contact"), payload)
        self.assertEqual(invalid.status_code, 302)
        self.assertEqual(Lead.objects.get(email="client@example.com").estimate_snapshot["services"][0]["status"], "review")

        payload = contact_payload(self.client, services=["deck-cleaning"], service_interest="", email="wood@example.com")
        payload["deck_material"] = "wood"
        valid = self.client.post(reverse("contact"), payload)
        self.assertRedirects(valid, reverse("contact"))
        lead = Lead.objects.get(email="wood@example.com")
        self.assertEqual(lead.selected_services, ["deck-cleaning"])
        self.assertEqual(lead.deck_material, "wood")

    def test_window_cleaning_page_has_approved_prices_and_commercial_link(self):
        response = self.client.get(reverse("service-detail", kwargs={"slug": "window-cleaning"}))
        self.assertContains(response, "MEANWHILE... THE NUMBERS!")
        self.assertContains(response, "Standard pricing on standard windows is $100 to come out + $10 per window.")
        self.assertNotContains(response, "$7 per window")
        self.assertContains(response, f'href="{reverse("commercial")}"')
        self.assertContains(response, 'id="pricing"')
        self.assertContains(response, "css/window-design.css")

    def test_window_design_renders_updated_cms_content_without_replacing_prices(self):
        service = Service.objects.get(slug="window-cleaning")
        service.summary = "A new summary written in the CMS."
        service.body = (
            "<h2>Fresh heading from the editor</h2>"
            "<p>Custom CMS description and a <a href='/services/'>service link</a>.</p>"
            "<section class='window-pricing'><h2>Today's prices</h2>"
            "<p>$100 visit + $10 per window</p></section>"
            "<h2>Another chapter</h2><p>Extra details from the editor.</p>"
        )
        service.save()
        response = self.client.get(service.get_absolute_url())
        self.assertContains(response, service.summary)
        self.assertContains(response, "Fresh heading from the editor")
        self.assertContains(response, "Extra details from the editor.")
        self.assertContains(response, "$100 visit + $10 per window")
        self.assertContains(response, "href='/services/'")
        self.assertContains(response, 'id="pricing"')

    def test_window_chapters_keep_their_design_after_cms_reordering(self):
        service = Service.objects.get(slug="window-cleaning")
        # Move existing marked HTML, rename a heading, insert an unmarked
        # chapter, and change a price just as an editor would.
        body = service.body
        intro, rest = body.split('<section class="window-pricing"', 1)
        pricing, rest = rest.split("</section>", 1)
        adventure, rest = rest.split('<h2 data-window-chapter="transparent"', 1)
        transparent, rest = rest.split('<h2 data-window-chapter="way"', 1)
        way, ready = rest.split('<h2 data-window-chapter="ready"', 1)
        service.body = (
            '<h2>New editorial chapter</h2><p>New copy stays visible.</p>'
            + '<h2 data-window-chapter="way"' + way
            + intro.replace("Wait... are the windows open?", "Look at that view!")
            + '<h2 data-window-chapter="ready"' + ready
            + '<section class="window-pricing"' + pricing.replace(
                "$100 to come out + $10 per window", "$125 visit + $11 per window"
            ) + "</section>"
            + adventure
            + '<h2 data-window-chapter="transparent"' + transparent
        )
        service.save()

        response = self.client.get(service.get_absolute_url())
        html = response.content.decode()
        self.assertContains(response, "New copy stays visible.")
        self.assertContains(response, "Look at that view!")
        self.assertContains(response, "$125 visit + $11 per window")
        self.assertNotIn("$100 to come out + $10 per window", html.split("<article", 1)[1])
        self.assertLess(html.index("window-other"), html.index("window-way"))
        self.assertLess(html.index("window-way"), html.index("window-intro"))
        self.assertLess(html.index("window-intro"), html.index("window-ready"))
        self.assertLess(html.index("window-ready"), html.index("window-pricing"))
        self.assertLess(html.index("window-pricing"), html.index("window-adventure"))
        self.assertLess(html.index("window-adventure"), html.index("window-transparent"))
        self.assertEqual(html.count('id="pricing"'), 1)
        self.assertEqual(html.count("window-final-action"), 1)
        self.assertLess(html.index("window-ready"), html.index("window-final-action"))
        self.assertLess(html.index("window-final-action"), html.index("window-pricing"))

    @override_settings(
        ENABLE_RECAPTCHA=True,
        RECAPTCHA_SITE_KEY="test-site-key",
        RECAPTCHA_SECRET_KEY="test-secret-key",
    )
    def test_contact_page_loads_invisible_recaptcha_v3(self):
        RecaptchaIntegration.objects.update_or_create(
            singleton_key="default",
            defaults={
                "site_key": "test-site-key",
                "minimum_score": 0.5,
                "allowed_hostnames": "vossomewindowcleaning.com",
                "is_enabled": True,
            },
        )
        response = self.client.get(reverse("contact"))

        self.assertContains(
            response,
            'data-recaptcha-site-key="test-site-key"',
        )
        self.assertContains(response, 'name="recaptcha_token"')
        self.assertContains(
            response,
            "https://www.google.com/recaptcha/api.js?render=test-site-key",
        )

    def test_analytics_bootstrap_uses_first_party_javascript(self):
        site_settings = SiteSettings.objects.first()
        site_settings.analytics_measurement_id = "G-TEST123"
        site_settings.save(update_fields=["analytics_measurement_id", "updated_at"])
        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            'data-analytics-measurement-id="G-TEST123"',
        )
        self.assertNotContains(response, "window.dataLayer=window.dataLayer")

    @override_settings(
        ENABLE_RECAPTCHA=True,
        RECAPTCHA_SITE_KEY="test-site-key",
        RECAPTCHA_SECRET_KEY="test-secret-key",
    )
    @patch("core.views.deliver_lead_to_anthem")
    @patch("core.views.send_lead_notification")
    @patch("core.views.verify_contact_recaptcha", return_value=False)
    def test_failed_recaptcha_is_not_saved_or_forwarded(
        self,
        verify_recaptcha,
        send_email,
        deliver_to_anthem,
    ):
        RecaptchaIntegration.objects.update_or_create(
            singleton_key="default",
            defaults={
                "site_key": "test-site-key",
                "minimum_score": 0.5,
                "allowed_hostnames": "vossomewindowcleaning.com",
                "is_enabled": True,
            },
        )
        response = self.client.post(
            reverse("contact"),
            contact_payload(
                self.client,
                recaptcha_token="rejected-token",
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "We could not verify this submission.",
            status_code=400,
        )
        self.assertFalse(Lead.objects.filter(email="client@example.com").exists())
        called_token, called_config = verify_recaptcha.call_args.args
        self.assertEqual(called_token, "rejected-token")
        self.assertEqual(called_config.site_key, "test-site-key")
        deliver_to_anthem.assert_not_called()
        send_email.assert_not_called()

    def test_contact_form_normalizes_us_phone_and_rejects_invalid_phone(self):
        valid = self.client.post(
            reverse("contact"),
            contact_payload(self.client, phone="+1 (314) 555-0199"),
        )
        self.assertEqual(valid.status_code, 302)
        self.assertEqual(Lead.objects.get(email="client@example.com").phone, "3145550199")

        invalid = self.client.post(
            reverse("contact"),
            contact_payload(
                self.client,
                email="invalid-phone@example.com",
                phone="555-0199",
            ),
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(
            Lead.objects.filter(email="invalid-phone@example.com").exists()
        )

    @patch("core.views.deliver_lead_to_anthem")
    @patch("core.views.send_lead_notification")
    def test_duplicate_browser_submission_is_saved_and_delivered_only_once(
        self,
        send_email,
        deliver_to_anthem,
    ):
        payload = contact_payload(self.client)

        first = self.client.post(reverse("contact"), payload)
        second = self.client.post(reverse("contact"), payload)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Lead.objects.filter(email="client@example.com").count(), 1)
        deliver_to_anthem.assert_not_called()
        send_email.assert_called_once()

    @patch("core.views.deliver_lead_to_anthem")
    @patch("core.views.send_lead_notification")
    def test_contact_submission_rate_limit_blocks_excess_attempts(
        self,
        send_email,
        deliver_to_anthem,
    ):
        responses = []
        for index in range(11):
            responses.append(
                self.client.post(
                    reverse("contact"),
                    contact_payload(
                        self.client,
                        email=f"client-{index}@example.com",
                    ),
                    REMOTE_ADDR="203.0.113.50",
                )
            )

        self.assertEqual(responses[-1].status_code, 429)
        self.assertEqual(Lead.objects.count(), 10)
        self.assertEqual(deliver_to_anthem.call_count, 0)
        self.assertEqual(send_email.call_count, 10)

    @override_settings(TRUST_PROXY_CLIENT_IP_HEADER=True)
    @patch("core.views.deliver_lead_to_anthem")
    @patch("core.views.send_lead_notification")
    def test_forwarded_header_prefix_cannot_bypass_rate_limit(
        self,
        send_email,
        deliver_to_anthem,
    ):
        responses = []
        for index in range(11):
            responses.append(
                self.client.post(
                    reverse("contact"),
                    contact_payload(
                        self.client,
                        email=f"forwarded-{index}@example.com",
                    ),
                    REMOTE_ADDR="10.0.0.4",
                    HTTP_X_FORWARDED_FOR=(
                        f"192.0.2.{index + 1}, 198.51.100.20"
                    ),
                )
            )

        self.assertEqual(responses[-1].status_code, 429)
        self.assertEqual(
            Lead.objects.filter(email__startswith="forwarded-").count(),
            10,
        )
        self.assertEqual(deliver_to_anthem.call_count, 0)
        self.assertEqual(send_email.call_count, 10)

    def test_header_and_footer_include_required_navigation(self):
        response = self.client.get(reverse("home"))

        for label in ["Home", "About us", "Services", "FAQ", "Blog", "Get a Quote"]:
            with self.subTest(label=label):
                self.assertContains(response, label)
        self.assertContains(
            response,
            '<nav aria-label="Footer navigation"><h3>Explore</h3>'
            f'<a href="{reverse("blog")}">Blog</a>'
            f'<a href="{reverse("services")}">Services</a>'
            f'<a href="{reverse("faq")}">FAQ</a>'
            "</nav>",
            html=True,
        )

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
        pages = [self.client.get(reverse("home")), self.client.get(reverse("commercial"))]
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

    def test_client_approved_window_cleaning_copy_can_be_edited_in_admin(self):
        service = Service.objects.get(slug="window-cleaning")
        self.assertLess(service.word_count, 650)
        service.full_clean()

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

    def test_seeded_pricing_guide_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="professional-window-cleaning-cost-guide")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "professional window cleaning cost")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>Professional Window Cleaning Cost Guide | Prices &amp; Estimates</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="How much does professional window cleaning cost? Explore typical prices per window, square foot rates, add-on costs, and what to expect on your estimate."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Average Window Cleaning Costs at a Glance")
        self.assertContains(detail_response, "The 3 Most Common Window Cleaning Pricing Models")
        self.assertContains(detail_response, "Enjoy Clear, Streak-Free Views with Vossome Window Cleaning")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_hard_water_stain_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="how-to-remove-hard-water-stains-from-windows")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "how to remove hard water stains from windows")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>How to Remove Hard Water Stains from Windows | DIY &amp; Pro Guide</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Struggling with stubborn white spots on your glass? Learn how to remove hard water stains from windows safely without scratching or permanently damaging your panes."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Why Do Hard Water Stains Form on Exterior Windows?")
        self.assertContains(detail_response, "Stage 1 vs. Stage 2 Damage: Staining vs. Glass Etching")
        self.assertContains(detail_response, "Restore Your Glass to Crystal Clarity with Vossome Window Cleaning")
        # Also verify the sidebar links to Blog #1 in More Homeowner Guides
        self.assertContains(detail_response, "/blog/professional-window-cleaning-cost-guide/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_pressure_vs_soft_washing_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="pressure-washing-vs-soft-washing")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "pressure washing vs soft washing")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>Pressure Washing vs. Soft Washing | Which Does Your Home Need?</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Confused about pressure washing vs. soft washing? Learn the key differences in PSI, cleaning solutions, and which surfaces require low-pressure soft washing."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Quick Comparison: Pressure Washing vs. Soft Washing at a Glance")
        self.assertContains(detail_response, "Surface-by-Surface Guide: Which Method Should You Use?")
        self.assertContains(detail_response, "Protect and Beautify Your Home with Vossome Window Cleaning")
        self.assertContains(detail_response, "/blog/professional-window-cleaning-cost-guide/")
        self.assertContains(detail_response, "/blog/how-to-remove-hard-water-stains-from-windows/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_pressure_washing_cost_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="how-much-does-it-cost-to-pressure-wash-a-house")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "how much does it cost to pressure wash a house")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(
            list_response,
            "The Complete Cost Guide to House Pressure Washing &amp; Driveway Cleaning",
        )
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>How Much Does It Cost to Pressure Wash a House? (Pricing Guide)</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Wondering how much does it cost to pressure wash a house or driveway? See average prices per square foot, siding rates, and bundle discounts in our complete guide."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Average House Pressure Washing Costs by Home Size")
        self.assertContains(detail_response, "Driveway, Sidewalk, and Concrete Patio Pressure Washing Costs")
        self.assertContains(detail_response, "Get a Fast, Transparent Pressure Washing Quote from Vossome Window Cleaning")
        self.assertContains(detail_response, "/blog/pressure-washing-vs-soft-washing/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_neglected_gutters_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="what-happens-if-you-dont-clean-gutters")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "what happens if you don't clean gutters")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>What Happens If You Don’t Clean Your Gutters? 7 Costly Disasters</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Wondering what happens if you don&#x27;t clean gutters? From cracked foundations and basement leaks to roof rot, see how a simple cleaning prevents $10k+ in repairs."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Cost Comparison: Routine Gutter Cleaning vs. Neglect Repairs")
        self.assertContains(detail_response, "The Domino Effect of a Clogged Downspout")
        self.assertContains(detail_response, "6 Warning Signs Your Gutters Are Secretly Clogged Right Now")
        self.assertContains(detail_response, "Protect Your Roof and Foundation with Vossome Window Cleaning")
        self.assertContains(detail_response, "/services/gutter-cleaning/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_gutter_cleaning_cost_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="gutter-cleaning-cost-per-foot")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "gutter cleaning cost per foot")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>Gutter Cleaning Cost Per Foot | 1, 2 &amp; 3-Story Price Guide</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="What is the average gutter cleaning cost per foot? See transparent 1-, 2-, and 3-story gutter cleaning prices, downspout flushing rates, and how to save."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Average Gutter Cleaning Costs at a Glance (By Home Stories &amp; Footage)")
        self.assertContains(detail_response, "6 Key Factors That Influence Gutter Cleaning Prices")
        self.assertContains(detail_response, "Get a Fast, Honest Gutter Cleaning Estimate from Vossome Window Cleaning")
        self.assertContains(detail_response, "/blog/what-happens-if-you-dont-clean-gutters/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_concrete_patio_stain_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="how-to-clean-concrete-patio-without-pressure-washer")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "how to clean concrete patio without pressure washer")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>How to Clean a Concrete Patio Without a Pressure Washer (Stain Guide)</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Learn how to clean a concrete patio without a pressure washer! Discover the best DIY scrubs for green algae, black mold, leaf stains, grease, and rust."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Why Does Concrete Stain So Easily? (The Rigid Sponge Effect)")
        self.assertContains(detail_response, "The Ultimate Patio Stain Removal Guide: 6 Common Stains &amp; How to Dissolve Them")
        self.assertContains(detail_response, "Save Your Back and Restore Your Patio with Vossome Window Cleaning")
        self.assertContains(detail_response, "/services/concrete-patio-cleaning/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_concrete_damage_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="can-pressure-washing-damage-concrete")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "can pressure washing damage concrete")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>Can Pressure Washing Damage Concrete? Avoiding Etching &amp; Scars</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Can pressure washing damage concrete? Learn how high PSI causes concrete etching, wand stripes, and spalling—plus how pros clean patios and driveways safely."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "4 Types of Concrete Damage Caused by Improper Pressure Washing")
        self.assertContains(detail_response, "The 5 Biggest Mistakes That Ruin Concrete Patios and Driveways")
        self.assertContains(detail_response, "Safe PSI Guidelines by Concrete Type")
        self.assertContains(detail_response, "Trust Your Concrete Patio &amp; Driveway to Vossome Window Cleaning")
        self.assertContains(detail_response, "/blog/how-to-clean-concrete-patio-without-pressure-washer/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_spring_maintenance_checklist_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="spring-exterior-home-maintenance-checklist")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "spring exterior home maintenance checklist")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(
            list_response,
            "The Ultimate Spring Exterior Home Maintenance Checklist: Windows, Gutters, Siding &amp; Patios",
        )
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>Spring Exterior Home Maintenance Checklist | Complete Guide</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Follow our ultimate spring exterior home maintenance checklist to protect your roof, gutters, siding, windows, and concrete patio after winter weather."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Why the Order of Your Spring Exterior Cleaning Matters")
        self.assertContains(detail_response, "Master Printable Summary: Your Spring Exterior Maintenance Schedule")
        self.assertContains(detail_response, "Check Off Your Entire Spring List in One Afternoon with Vossome Window Cleaning")
        self.assertContains(detail_response, "/blog/can-pressure-washing-damage-concrete/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_seeded_fall_maintenance_checklist_blog_renders_with_seo_metadata_and_sitemap(self):
        post = BlogPost.objects.get(slug="fall-gutter-and-roof-maintenance-checklist")
        post.full_clean()
        self.assertTrue(post.is_published)
        self.assertEqual(post.primary_keyword, "fall gutter and roof maintenance checklist")

        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, post.title)
        self.assertContains(list_response, post.get_absolute_url())

        detail_response = self.client.get(post.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "<title>Fall Gutter &amp; Roof Maintenance Checklist | Winter Prep Guide</title>",
            html=True,
        )
        self.assertContains(
            detail_response,
            'name="description" content="Follow our essential fall gutter and roof maintenance checklist! Learn how to prevent ice dams, protect concrete patios from spalling, and prep your home for winter."',
        )
        self.assertContains(detail_response, 'property="og:type" content="article"')
        self.assertContains(detail_response, "Priority #1: The Fall Gutter and Roof Maintenance Checklist")
        self.assertContains(detail_response, "Chronological Fall Exterior Maintenance Timeline (September &ndash; December)")
        self.assertContains(detail_response, "Prepare Your Home for Winter with Vossome Window Cleaning")
        self.assertContains(detail_response, "/blog/spring-exterior-home-maintenance-checklist/")

        sitemap_response = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertContains(sitemap_response, post.get_absolute_url())

    def test_all_blog_pages_render_hero_section_with_associated_image_and_overlaid_title(self):
        list_response = self.client.get(reverse("blog"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'class="blog-hero blog-hero--index"')
        self.assertContains(list_response, 'class="blog-hero-bg"')
        self.assertContains(list_response, 'class="blog-hero-shade"')
        self.assertContains(list_response, "<h1>Clear Advice for a Brighter View.</h1>", html=True)
        self.assertContains(list_response, 'class="blog-grid blog-card-grid"')
        self.assertContains(list_response, 'class="blog-card__media"')
        self.assertContains(list_response, 'class="blog-card__image"')
        self.assertContains(list_response, 'class="blog-card__overlay"')
        self.assertContains(list_response, 'class="blog-card__content"')

        expected_dates = [
            ("professional-window-cleaning-cost-guide", "October 26th, 2026"),
            ("how-to-remove-hard-water-stains-from-windows", "October 23rd, 2026"),
            ("pressure-washing-vs-soft-washing", "October 20th, 2026"),
            ("how-much-does-it-cost-to-pressure-wash-a-house", "October 17th, 2026"),
            ("what-happens-if-you-dont-clean-gutters", "October 14th, 2026"),
            ("gutter-cleaning-cost-per-foot", "October 11th, 2026"),
            ("how-to-clean-concrete-patio-without-pressure-washer", "October 8th, 2026"),
            ("can-pressure-washing-damage-concrete", "October 5th, 2026"),
            ("spring-exterior-home-maintenance-checklist", "October 2nd, 2026"),
            ("fall-gutter-and-roof-maintenance-checklist", "September 29th, 2026"),
        ]
        published_posts = list(BlogPost.objects.filter(is_published=True))
        self.assertEqual(
            [p.slug for p in published_posts],
            [slug for slug, _ in expected_dates],
        )
        expected_date_by_slug = dict(expected_dates)
        for post in published_posts:
            expected_date = expected_date_by_slug[post.slug]
            self.assertTrue(post.hero_image_static)
            self.assertTrue(post.hero_image_alt)
            self.assertContains(list_response, post.hero_image_static)
            self.assertContains(list_response, expected_date)
            self.assertContains(
                list_response,
                f'<h2 class="blog-card__title" itemprop="headline">{post.title}</h2>',
                html=True,
            )
            response = self.client.get(post.get_absolute_url())
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'class="blog-hero blog-hero--{post.slug}"')
            self.assertContains(response, 'class="blog-hero-bg"')
            self.assertContains(response, 'class="blog-hero-shade"')
            self.assertContains(response, post.hero_image_static)
            self.assertContains(response, expected_date)
            self.assertContains(response, f'<h1 itemprop="headline">{post.title}</h1>', html=True)
            self.assertContains(response, 'class="blog-related-section"')


