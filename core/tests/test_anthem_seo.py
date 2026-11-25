import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings

from anthem_seo.blogs import sync_anthem_blogs
from anthem_seo.contract import clear_bundle_cache, load_bundle
from anthem_seo.resolver import resolve_request_overrides
from anthem_seo.routing import enforce_route
from core.models import BlogPost, Page, Service


def _make_words(count=700):
    return "<p>" + " ".join(f"word{i}" for i in range(count)) + "</p>"


class AnthemSeoTemplateTests(TestCase):
    def setUp(self):
        clear_bundle_cache()
        self.factory = RequestFactory()

    def tearDown(self):
        clear_bundle_cache()

    def test_default_bundle_loads_and_status_endpoint_authenticated(self):
        bundle = load_bundle(force_reload=True)
        self.assertEqual(bundle["manifest"]["contract_version"], 1)

        with override_settings(ANTHEM_SEO_DISCOVERY_TOKEN="secret-token"):
            unauth = self.client.get("/api/seo/capabilities/")
            self.assertEqual(unauth.status_code, 401)

            auth = self.client.get(
                "/api/seo/capabilities/",
                HTTP_AUTHORIZATION="Bearer secret-token",
            )
            self.assertEqual(auth.status_code, 200)
            payload = auth.json()
            self.assertEqual(payload["cms"], "django-cms")
            self.assertEqual(payload["contract_version"], 1)

    def test_sync_anthem_blogs_upserts_blogpost_without_650_word_constraint(self):
        base_bundle = load_bundle(force_reload=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            seo_dir = Path(tmpdir)
            (seo_dir / "pages").mkdir()
            (seo_dir / "posts").mkdir()
            manifest = copy.deepcopy(base_bundle["manifest"])
            manifest["bindings"].append(
                {
                    "item_id": "blog-short-update",
                    "language": "en-us",
                    "kind": "page",
                    "cms_ref": {"reverse_id": "blog-short-update"},
                }
            )
            (seo_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (seo_dir / "redirects.json").write_text(json.dumps([]), encoding="utf-8")
            page_payload = {
                "contract_version": 1,
                "item_id": "blog-short-update",
                "language": "en-us",
                "kind": "page",
                "cms_ref": {"reverse_id": "blog-short-update"},
                "seo": {
                    "seo_title": "Short Blog Update | Test Site",
                    "meta_description": "Short blog post description.",
                    "canonical": "https://example.com/blog/short-update/",
                    "og_title": "Short Blog Update",
                    "og_description": "Short blog post description.",
                    "og_image": "https://example.com/static/website/blog/short-update.png",
                    "og_type": "article",
                    "twitter_card": "summary_large_image",
                    "twitter_title": "Short Blog Update",
                    "twitter_description": "Short blog post description.",
                },
                "faq": {
                    "section_title": "Common Questions",
                    "faqs": [
                        {
                            "question": "Is BlogPost separate from Page/Service word count?",
                            "answer": "<p>Yes, BlogPost has no 650-900 word constraint.</p>",
                        }
                    ],
                },
            }
            (seo_dir / "pages" / "blog-short-update.en-us.json").write_text(
                json.dumps(page_payload), encoding="utf-8"
            )
            post_payload = {
                "contract_version": 1,
                "item_id": "blog-short-update",
                "language": "en-us",
                "kind": "post",
                "cms_ref": {"reverse_id": "blog-short-update"},
                "post": {
                    "title": "Short Blog Update",
                    "slug": "short-update",
                    "summary": "A brief summary.",
                    "body_html": "<p>This blog post is intentionally under 650 words.</p><script>alert(1)</script>",
                    "status": "publish",
                    "published_at": "2026-10-15T12:00:00Z",
                    "author_name": "Anthem Bot",
                    "featured_image": "/static/website/blog/short-update.png",
                    "featured_image_alt": "Short update hero",
                    "topics": ["Maintenance", "Tips"],
                },
            }
            (seo_dir / "posts" / "blog-short-update.en-us.json").write_text(
                json.dumps(post_payload), encoding="utf-8"
            )

            with patch("anthem_seo.contract.bundle_root", return_value=seo_dir):
                clear_bundle_cache()
                bundle = load_bundle(force_reload=True)
                result = sync_anthem_blogs(bundle=bundle)
                self.assertEqual(result["synced"], 1)

                post = BlogPost.objects.get(source_guid="anthem:blog-short-update")
                self.assertEqual(post.title, "Short Blog Update")
                self.assertEqual(post.slug, "short-update")
                self.assertTrue(post.is_published)
                self.assertNotIn("<script>", post.body)
                self.assertEqual(post.topics.count(), 2)

                request = self.factory.get("/blog/short-update/", HTTP_HOST="example.com")
                resolved = resolve_request_overrides(request)
                self.assertEqual(
                    resolved["anthem_seo_override"]["seo_title"],
                    "Short Blog Update | Test Site",
                )
                self.assertEqual(len(resolved["managed_faq"]["faqs"]), 1)
                self.assertEqual(
                    resolved["managed_faq"]["faqs"][0]["answer"],
                    "Yes, BlogPost has no 650-900 word constraint.",
                )
                self.assertIn("FAQPage", resolved["faq_json_ld"])
                self.assertNotIn("<p>", resolved["faq_json_ld"])

                service_request = self.factory.get(
                    "/services/short-update/", HTTP_HOST="example.com"
                )
                self.assertEqual(
                    resolve_request_overrides(service_request)["anthem_seo_override"],
                    {},
                )

    def test_discovery_lists_static_routes_pages_services_and_posts(self):
        Page.objects.create(
            title="Emergency Plumbing",
            slug="emergency-plumbing",
            body=_make_words(700),
            is_published=True,
        )
        Service.objects.create(
            title="Drain Cleaning",
            slug="drain-cleaning",
            body=_make_words(700),
            is_published=True,
        )
        with override_settings(ANTHEM_SEO_DISCOVERY_TOKEN="secret-token"):
            resp = self.client.get(
                "/api/seo/pages/",
                HTTP_AUTHORIZATION="Bearer secret-token",
            )
            self.assertEqual(resp.status_code, 200)
            items = resp.json()["results"]
            item_ids = {item["item_id"] for item in items}
            self.assertIn("page-home", item_ids)
            self.assertIn("cms:page-emergency-plumbing", item_ids)
            self.assertIn("cms:svc-drain-cleaning", item_ids)

    def test_unoverridden_route_uses_zero_db_queries(self):
        request = self.factory.get("/blog/some-article/", HTTP_HOST="example.com")
        with self.assertNumQueries(0):
            redirect_resp = enforce_route(request)
            self.assertIsNone(redirect_resp)
            resolved = resolve_request_overrides(request)
            self.assertEqual(resolved["anthem_seo_override"], {})
