import base64
import json
import time
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from anthem_seo.emm import decode_pairing_code, resolve_emm_config, sign_site_request
from core.models import BlogPost, BlogTopic


def _make_pairing_code(site_id="django-site-999", token="secret-token-123"):
    payload = {
        "endpoint": "https://live.anthemcrm.com/api/v1/wordpress-seo/django-cms/connectors/poll/",
        "home_url": "https://example.com",
        "site_id": site_id,
        "token": token,
    }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return f"EVC1.{encoded}"


class EmmConnectorTests(TestCase):
    def test_decode_pairing_code_and_resolve_config(self):
        code = _make_pairing_code(site_id="django-site-42", token="tok-abc")
        decoded = decode_pairing_code(code)
        self.assertEqual(decoded["site_id"], "django-site-42")
        self.assertEqual(decoded["token"], "tok-abc")

        with override_settings(
            EMM_PAIRING_CODE=code,
            EMM_SITE_ID="",
            ANTHEM_SEO_DISCOVERY_TOKEN="",
        ):
            cfg = resolve_emm_config()
            self.assertEqual(cfg["site_id"], "django-site-42")
            self.assertEqual(cfg["secret"], "tok-abc")
            self.assertIn("connectors/poll/", cfg["endpoint"])

    def test_emm_wake_get_and_signed_post(self):
        code = _make_pairing_code(site_id="django-site-42", token="tok-abc")
        with override_settings(
            EMM_PAIRING_CODE=code,
            EMM_SITE_ID="",
            ANTHEM_SEO_DISCOVERY_TOKEN="",
        ):
            get_resp = self.client.get("/emm/wake/")
            self.assertEqual(get_resp.status_code, 200)
            self.assertTrue(get_resp.json()["ok"])

            # Unsigned POST rejected
            bad_resp = self.client.post(
                "/emm/wake/",
                data=b"{}",
                content_type="application/json",
            )
            self.assertEqual(bad_resp.status_code, 401)

            # Signed POST triggers poll_once and returns ok: True
            raw_body = b"{}"
            stamp = str(int(time.time()))
            sig = sign_site_request("django-site-42", "tok-abc", stamp, raw_body)
            with patch(
                "anthem_seo.emm_views.poll_once",
                return_value={
                    "ok": True,
                    "site_id": "django-site-42",
                    "revision": "1",
                    "commands_processed": 0,
                    "results": [],
                },
            ) as mock_poll:
                ok_resp = self.client.post(
                    "/emm/wake/",
                    data=raw_body,
                    content_type="application/json",
                    HTTP_X_EMM_SITE="django-site-42",
                    HTTP_X_EMM_TIMESTAMP=stamp,
                    HTTP_X_EMM_SIGNATURE=sig,
                )
            self.assertEqual(ok_resp.status_code, 200)
            body = ok_resp.json()
            self.assertTrue(body["ok"])
            self.assertEqual(body["status"], "ok")
            mock_poll.assert_called_once()

    def test_emm_publish_creates_and_updates_blog_post(self):
        code = _make_pairing_code(site_id="django-site-42", token="tok-abc")
        payload = {
            "title": "Estate Planning Basics",
            "slug": "estate-planning-basics",
            "content": "<p>Hello world</p>",
            "status": "publish",
            "excerpt": "Short summary",
            "category": "Estate Law",
            "meta": {
                "seo_title": "Estate Planning Basics | Firm",
                "meta_description": "Learn estate planning basics.",
                "canonical_url": "https://example.com/blog/estate-planning-basics/",
            },
            "featured_image_b64": base64.b64encode(b"fake-png-bytes").decode("ascii"),
            "featured_image_filename": "estate.png",
        }
        raw_body = json.dumps(payload).encode("utf-8")
        stamp = str(int(time.time()))
        sig = sign_site_request("django-site-42", "tok-abc", stamp, raw_body)

        with override_settings(
            EMM_PAIRING_CODE=code,
            EMM_SITE_ID="",
            ANTHEM_SEO_DISCOVERY_TOKEN="",
        ):
            resp = self.client.post(
                "/emm/api/v1/publish/",
                data=raw_body,
                content_type="application/json",
                HTTP_X_EMM_SITE="django-site-42",
                HTTP_X_EMM_TIMESTAMP=stamp,
                HTTP_X_EMM_SIGNATURE=sig,
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["slug"], "estate-planning-basics")

        post = BlogPost.objects.get(slug="estate-planning-basics")
        self.assertTrue(post.is_published)
        self.assertEqual(post.meta_title, "Estate Planning Basics | Firm")
        self.assertTrue(bool(post.featured_image))
        self.assertTrue(BlogTopic.objects.filter(name="Estate Law").exists())

    def test_emm_connect_management_command(self):
        from anthem_seo.contract import bundle_root

        manifest_path = bundle_root() / "manifest.json"
        original_manifest = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        try:
            code = _make_pairing_code(site_id="django-site-42", token="tok-abc")
            out = StringIO()
            with patch(
                "anthem_seo.management.commands.emm_connect.register_connector",
                return_value={"client_secret": "real-secret"},
            ) as mock_reg, patch(
                "anthem_seo.management.commands.emm_connect.poll_once",
                return_value={"ok": True, "commands_processed": 1},
            ) as mock_poll:
                call_command("emm_connect", code, stdout=out)
            mock_reg.assert_called_once()
            self.assertEqual(mock_poll.call_count, 2)
            self.assertIn("Connected and polled Anthem CRM", out.getvalue())
        finally:
            if original_manifest is not None:
                manifest_path.write_text(original_manifest, encoding="utf-8")
