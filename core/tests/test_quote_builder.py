from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.forms import LeadForm
from core.models import Lead, LeadPhoto
from core.pricing import estimate_quote


class PricingTests(SimpleTestCase):
    def row(self, service, **details):
        return estimate_quote([service], details)["services"][0]

    def test_window_count_and_unknown(self):
        self.assertEqual(self.row("window-cleaning", window_count=20)["amount"], "300.00")
        for details in ({}, {"window_count": 0}, {"window_count": 20, "window_unknown": True}):
            self.assertIsNone(self.row("window-cleaning", **details)["amount"])

    def test_gutter_weights_and_single_minimum(self):
        self.assertEqual(self.row("gutter-cleaning", gutter_one=100, gutter_three=50)["amount"], "250.00")
        self.assertEqual(self.row("gutter-cleaning", gutter_one_half=200)["amount"], "300.00")
        self.assertEqual(self.row("gutter-cleaning", gutter_one=20, gutter_two=10)["amount"], "180.00")
        self.assertIsNone(self.row("gutter-cleaning")["amount"])
        self.assertIsNone(self.row("gutter-cleaning", gutter_one=200, gutter_unknown=True)["amount"])

    def test_house_only_all_no_produces_flat_rate(self):
        self.assertIsNone(self.row("pressure-washing")["amount"])
        self.assertEqual(self.row("pressure-washing", house_three_stories="no", house_large="no", house_roof="no")["amount"], "400.00")
        for answer in ("yes", "unsure", ""):
            self.assertIsNone(self.row("pressure-washing", house_three_stories=answer, house_large="no", house_roof="no")["amount"])

    def test_surface_area_dimensions_and_unknown(self):
        self.assertEqual(self.row("concrete-patio-cleaning", surface_area=500)["amount"], "200.00")
        self.assertEqual(self.row("concrete-patio-cleaning", surface_length=25, surface_width=20)["amount"], "200.00")
        self.assertIsNone(self.row("concrete-patio-cleaning", surface_length=25)["amount"])
        self.assertIsNone(self.row("concrete-patio-cleaning", surface_area=500, surface_unknown=True)["amount"])

    def test_deck_no_partial_or_extras_in_complete_total(self):
        row = self.row("deck-cleaning", deck_area=200, deck_railing=50, deck_material="composite")
        self.assertEqual(row["amount"], "200.00")
        self.assertEqual(row["status"], "estimate")
        self.assertIsNone(self.row("deck-cleaning", deck_area=200)["amount"])
        for flag in ("deck_stairs", "deck_underside"):
            row = self.row("deck-cleaning", deck_area=200, deck_railing=50, deck_material="wood", **{flag: True})
            self.assertEqual(row["amount"], "200.00")
            self.assertEqual(row["status"], "review")
            self.assertIn("NOT included", " ".join(row["reasons"]))

    def test_combination_applies_window_visit_fee_once_and_flags_unknown(self):
        snapshot = estimate_quote(["window-cleaning", "gutter-cleaning", "pressure-washing"], {
            "window_count": 20, "gutter_one": 200,
            "house_three_stories": "no", "house_large": "no", "house_roof": "no",
        })
        self.assertEqual(snapshot["estimated_subtotal"], "900.00")
        self.assertTrue(snapshot["complete"])
        self.assertFalse(estimate_quote(["window-cleaning", "other"], {"window_count": 20})["complete"])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", PRIVATE_OBJECT_DIR="")
class InquiryTests(TestCase):
    def payload(self, **values):
        self.client.get(reverse("contact"))
        result = {
            "first_name": "Quote", "last_name": "Test",
            "service_address": "123 Test Street, St. Charles, MO",
            "preferred_reply_method": "text", "phone": "3145550100",
            "services": ["window-cleaning"], "window_count": "20",
            "submission_token": self.client.session["contact_submission_token"],
        }
        result.update(values)
        return result

    def submit(self, **values):
        return self.client.post(reverse("contact"), self.payload(**values))

    def test_phone_only_saves_all_details_and_emails_no_replyto(self):
        with patch("core.views.deliver_lead_to_anthem") as crm:
            response = self.submit()
        self.assertEqual(response.status_code, 302)
        lead = Lead.objects.get()
        self.assertEqual(lead.email, "")
        self.assertEqual(lead.service_address, "123 Test Street, St. Charles, MO")
        self.assertEqual(lead.quote_details["window_count"], 20)
        self.assertEqual(lead.estimate_snapshot["services"][0]["amount"], "300.00")
        self.assertEqual(lead.email_notification_status, "sent")
        self.assertEqual(mail.outbox[0].reply_to, [])
        self.assertIn("$300.00 ballpark estimate", mail.outbox[0].body)
        self.assertIn(lead.service_address, mail.outbox[0].body)
        self.assertIn("No appointment has been booked", mail.outbox[0].body)
        crm.assert_not_called()
        self.assertEqual(lead.anthem_delivery_status, "needs_review")

    def test_email_only_and_method_required(self):
        response = self.submit(preferred_reply_method="email", phone="", email="quote@example.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mail.outbox[0].reply_to, ["quote@example.com"])
        self.assertEqual(self.submit(preferred_reply_method="").status_code, 200)

    def test_address_and_selected_contact_are_required_not_notes_or_counts(self):
        self.assertEqual(self.submit(service_address="").status_code, 200)
        self.assertEqual(self.submit(phone="").status_code, 200)
        self.assertEqual(self.submit(preferred_reply_method="email", email="", phone="").status_code, 200)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(self.submit(window_count="").status_code, 302)
        self.assertIsNone(Lead.objects.get().estimate_snapshot["services"][0]["amount"])

    def test_unknown_or_deselected_measurements_cannot_override_estimate(self):
        self.assertEqual(self.submit(window_unknown="on", window_count="-5", gutter_one="-500", estimated_total="1").status_code, 302)
        lead = Lead.objects.get()
        self.assertNotIn("gutter_one", lead.quote_details)
        self.assertIsNone(lead.estimate_snapshot["services"][0]["amount"])

    def test_negative_and_fractional_window_counts_rejected(self):
        for count in ("-1", "1.5", "NaN", "Infinity"):
            self.assertEqual(self.submit(window_count=count).status_code, 200)
        self.assertEqual(Lead.objects.count(), 0)

    def test_deck_flags_and_access_reach_email(self):
        response = self.submit(services=["deck-cleaning"], deck_area="200", deck_railing="50", deck_material="wood", deck_stairs="on", deck_underside="on", deck_access="Use side gate")
        self.assertEqual(response.status_code, 302)
        body = mail.outbox[0].body
        for value in ("$200.00", "NOT included", "Use side gate", "Deck material: Wood", "Stairs", "Underside"):
            self.assertIn(value, body)

    @patch("core.views.EmailMessage.send", side_effect=RuntimeError("offline"))
    def test_email_failure_keeps_inquiry_with_visible_admin_status(self, send):
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(Lead.objects.get().email_notification_status, "failed")

    def photo_upload(self):
        image = BytesIO()
        Image.new("RGB", (20, 20), "blue").save(image, format="PNG")
        return SimpleUploadedFile("project.png", image.getvalue(), content_type="image/png")

    def test_photos_are_sanitized_email_attachments_without_storage(self):
        with patch("core.lead_storage.PrivateLeadStorage.save", side_effect=AssertionError("New photos must not be stored")):
            self.assertEqual(self.submit(photos=[self.photo_upload(), self.photo_upload()]).status_code, 302)
        self.assertEqual(LeadPhoto.objects.count(), 0)
        self.assertEqual(Lead.objects.get().quote_details["photo_count"], 2)
        email = mail.outbox[0]
        self.assertEqual(len(email.attachments), 2)
        for index, attachment in enumerate(email.attachments, start=1):
            self.assertEqual(attachment.filename, f"project-photo-{index}.jpg")
            self.assertEqual(attachment.mimetype, "image/jpeg")
            self.assertEqual(Image.open(BytesIO(attachment.content)).format, "JPEG")
        self.assertIn("not retained by the website", email.body)
        self.assertNotIn("/inquiries/photos/", email.body)
        self.assertLess(len(email.message().as_bytes()), 10 * 1024 * 1024)

    @patch("core.views.EmailMessage.send", side_effect=RuntimeError("offline"))
    def test_photo_email_failure_saves_details_and_warns_to_send_directly(self, send):
        response = self.submit(photos=[self.photo_upload()])
        self.assertEqual(Lead.objects.get().email_notification_status, "failed")
        self.assertEqual(LeadPhoto.objects.count(), 0)
        self.assertContains(self.client.get(response.url), "we couldn’t email your photos")
        self.assertEqual(Lead.objects.get().quote_details["photo_count"], 1)

    @patch("core.views.EmailMessage.send", return_value=0)
    def test_zero_email_delivery_is_marked_failed(self, send):
        self.submit()
        self.assertEqual(Lead.objects.get().email_notification_status, "failed")

    @override_settings(LEAD_NOTIFICATION_EMAIL="")
    def test_missing_recipient_warns_photos_were_not_delivered(self):
        response = self.submit(photos=[self.photo_upload()])
        self.assertEqual(Lead.objects.get().email_notification_status, "disabled")
        self.assertContains(self.client.get(response.url), "we couldn’t email your photos")

    @patch("core.quote_fields.MAX_EMAIL_PHOTO_BYTES", 1)
    def test_attachment_batch_size_is_validated_before_saving(self):
        response = self.submit(photos=[self.photo_upload()])
        self.assertContains(response, "too large to email together")
        self.assertEqual(Lead.objects.count(), 0)

    def test_legacy_photo_authorized_download_still_works(self):
        self.submit()
        with TemporaryDirectory() as directory, override_settings(PRIVATE_LEAD_ROOT=directory):
            photo = LeadPhoto.objects.create(lead=Lead.objects.get(), image=self.photo_upload())
            url = reverse("lead-photo", kwargs={"pk": photo.pk})
            self.assertEqual(self.client.get(url).status_code, 302)
            User = get_user_model()
            user = User.objects.create_user(username="photo-staff", is_staff=True)
            self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
            self.assertEqual(self.client.get(url).status_code, 403)
            user.user_permissions.add(Permission.objects.get(codename="view_lead"))
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_bad_photo_rejected_without_losing_fields(self):
        bad = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
        response = self.submit(photos=[bad])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please use a valid JPG")
        self.assertEqual(Lead.objects.count(), 0)

    def test_public_copy_has_no_free_quote_or_outside_only(self):
        for path in ("/", "/contact/", "/services/", "/services/window-cleaning/", "/about/", "/faq/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            content = response.content.decode().lower()
            self.assertNotIn("free quote", content)
            self.assertNotIn("exterior-only", content)
            self.assertNotIn("$7 per window", content)
