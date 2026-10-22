import logging
import uuid
from datetime import timedelta
from hashlib import sha256
from ipaddress import ip_address

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.generic import DetailView

from .anthem import deliver_lead_to_anthem
from .forms import LeadForm
from .models import ContactSubmissionThrottle, FAQ, Page, Service, Lead, LeadPhoto
from .pricing import estimate_lines
from .recaptcha import get_contact_recaptcha_config, verify_contact_recaptcha


logger = logging.getLogger("security.contact")
CONTACT_SUBMISSION_TOKEN_KEY = "contact_submission_token"
CONTACT_RATE_LIMIT = 10
CONTACT_RATE_WINDOW_SECONDS = 15 * 60


def _contact_submission_token(request):
    token = request.session.get(CONTACT_SUBMISSION_TOKEN_KEY)
    if not token:
        token = str(uuid.uuid4())
        request.session[CONTACT_SUBMISSION_TOKEN_KEY] = token
    return token


def _contact_client_address(request):
    remote_address = request.META.get("REMOTE_ADDR", "")
    if settings.TRUST_PROXY_CLIENT_IP_HEADER:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            remote_address = forwarded_for.rsplit(",", 1)[-1].strip()
    try:
        return str(ip_address(remote_address))
    except ValueError:
        return "unknown"


def _contact_rate_limited(request):
    remote_address = _contact_client_address(request)
    digest = sha256(
        f"{settings.SECRET_KEY}:{remote_address}".encode("utf-8")
    ).hexdigest()
    now = timezone.now()
    window_cutoff = now - timedelta(seconds=CONTACT_RATE_WINDOW_SECONDS)
    with transaction.atomic():
        throttle, _ = ContactSubmissionThrottle.objects.select_for_update().get_or_create(
            fingerprint=digest,
            defaults={"window_started_at": now, "attempts": 0},
        )
        if throttle.window_started_at < window_cutoff:
            throttle.window_started_at = now
            throttle.attempts = 0
        if throttle.attempts >= CONTACT_RATE_LIMIT:
            return True
        throttle.attempts += 1
        throttle.save(update_fields=["window_started_at", "attempts"])
    return False


def _contact_context(request, form, recaptcha_config):
    return {
        "form": form,
        "contact_submitted": request.session.pop(
            "contact_submitted",
            False,
        ),
        "recaptcha_enabled": recaptcha_config is not None,
        "recaptcha_site_key": (
            recaptcha_config.site_key if recaptcha_config else ""
        ),
        "estimated_quote": getattr(form, "estimated_quote", None),
    }


def send_lead_notification(lead, photos=()):
    """Send transient photo attachments; never persist new customer photos."""
    if not settings.LEAD_NOTIFICATION_EMAIL:
        lead.email_notification_status = "disabled"
        lead.save(update_fields=["email_notification_status"])
        for photo in photos:
            photo.close()
        return False

    consent = "Yes" if lead.consent_to_contact else "No"
    body = "\n".join(
        [
            "A new contact-form lead was submitted on the Vossome website.",
            "",
            f"First name: {lead.first_name}",
            f"Last name: {lead.last_name}",
            f"Email: {lead.email}",
            f"Phone: {lead.phone or 'Not provided'}",
            f"Service address: {lead.service_address}",
            f"Services: {', '.join(lead.selected_service_labels) or 'Not specified'}",
            f"Deck material: {lead.get_deck_material_display() or 'Not specified'}",
            f"Preferred reply: {lead.get_preferred_reply_method_display() or 'No preference'}",
            f"Consent to contact: {consent}",
            f"Source: {lead.source or 'website'}",
            "",
            "Message:",
            lead.message,
            "",
            "Pricing details (customer measurements are approximate):",
            *[f"{key.replace('_', ' ').capitalize()}: {value}" for key, value in lead.quote_details.items() if value not in (None, "")],
            "",
            estimate_lines(lead.estimate_snapshot),
            "",
            f"Photos: {len(photos)} JPEG attachment(s)." if photos else "No photos supplied.",
            "Customer photos are emailed as attachments, not retained by the website.",
            "",
            "This is an inquiry, not a booked appointment or marketing subscription.",
        ]
    )
    message = EmailMessage(
        subject=f"New Vossome {', '.join(lead.selected_service_labels) or 'website'} lead: {lead.full_name}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.LEAD_NOTIFICATION_EMAIL],
        reply_to=[lead.email] if lead.email else [],
    )
    try:
        for index, photo in enumerate(photos, start=1):
            photo.seek(0)
            message.attach(f"project-photo-{index}.jpg", photo.read(), "image/jpeg")
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("The email backend did not accept the notification.")
        lead.email_notification_status = "sent"
    except Exception:
        logger.exception("Lead notification email failed for lead_id=%s", lead.pk)
        lead.email_notification_status = "failed"
    finally:
        for photo in photos:
            photo.close()
    lead.save(update_fields=["email_notification_status"])
    return lead.email_notification_status == "sent"


@staff_member_required
@require_GET
def lead_photo(request, pk):
    photo = get_object_or_404(LeadPhoto, pk=pk)
    if not request.user.has_perm("core.view_lead"):
        return HttpResponse(status=403)
    response = FileResponse(photo.image.open("rb"), as_attachment=True, filename="vossome-project-photo.jpg")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def healthz(request):
    return JsonResponse({"status": "ok"})


@require_GET
def robots_txt(request):
    lines = ["User-agent: *", "Allow: /", "Sitemap: /sitemap.xml"]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def home(request):
    return render(
        request,
        "home.html",
        {"services": Service.objects.filter(is_published=True)[:6]},
    )


def about(request):
    page = Page.objects.filter(slug="about", is_published=True).first()
    return render(request, "about.html", {"page": page})


def services(request):
    return render(
        request,
        "services.html",
        {"services": Service.objects.filter(is_published=True)},
    )


def commercial(request):
    return render(request, "commercial.html")


def faq(request):
    return render(
        request,
        "faq.html",
        {"faqs": FAQ.objects.filter(is_published=True)},
    )


class PageDetailView(DetailView):
    model = Page
    template_name = "page_detail.html"

    def get_queryset(self):
        return Page.objects.filter(is_published=True)


class ServiceDetailView(DetailView):
    model = Service
    template_name = "service_detail.html"

    def get_queryset(self):
        return Service.objects.filter(is_published=True)


def contact(request):
    recaptcha_config = get_contact_recaptcha_config()
    submission_token = _contact_submission_token(request)
    form = LeadForm(
        request.POST or None,
        request.FILES or None,
        initial={"submission_token": submission_token},
        expected_submission_token=submission_token,
    )
    if request.method == "POST" and form.is_valid():
        if _contact_rate_limited(request):
            messages.error(
                request,
                "Too many requests were submitted. Please call or text us instead.",
            )
            return render(
                request,
                "contact.html",
                _contact_context(request, form, recaptcha_config),
                status=429,
            )
        if not verify_contact_recaptcha(
            request.POST.get("recaptcha_token", ""),
            recaptcha_config,
        ):
            form.add_error(
                None,
                "We could not verify this submission. Please try again or call us.",
            )
            return render(
                request,
                "contact.html",
                _contact_context(request, form, recaptcha_config),
                status=400,
            )
        lead = form.save(commit=False)
        lead.source = request.POST.get("source", "website")[:120]
        lead.submission_token = form.cleaned_data["submission_token"]
        photos = form.cleaned_data.get("photos", [])
        if photos:
            lead.quote_details["photo_count"] = len(photos)
            lead.quote_details["photo_handling"] = "Email attachments only; not retained by website."
        try:
            with transaction.atomic():
                lead.save()
        except IntegrityError:
            messages.success(request, "Your request has been received. A real human on the Vossome team will review it and follow up. No appointment has been booked.")
            request.session["contact_submitted"] = True
            request.session.pop(CONTACT_SUBMISSION_TOKEN_KEY, None)
            return redirect("contact")
        except Exception:
            logger.exception("Inquiry save failed; no email or CRM submission was attempted.")
            form.add_error(None, "We couldn’t save your request or photos. Please try again, or text or call the team. If you selected photos, please select them again.")
            return render(request, "contact.html", _contact_context(request, form, recaptcha_config), status=503)
        request.session.pop(CONTACT_SUBMISSION_TOKEN_KEY, None)
        # Keep this form's CRM handoff unchanged until explicitly enabled.
        lead.anthem_delivery_status = Lead.AnthemDeliveryStatus.NEEDS_REVIEW
        lead.anthem_error_summary = "Quote inquiry saved; automatic CRM handoff is not enabled for this form."
        lead.save(update_fields=["anthem_delivery_status", "anthem_error_summary"])
        emailed = send_lead_notification(lead, photos)
        if not emailed:
            if photos:
                messages.warning(request, "Your project details were saved, but we couldn’t email your photos. The website has not retained them. Please text or email the photos directly to Vossome.")
            else:
                messages.warning(request, "Your project details were saved, but we couldn’t send the team’s email notification. Please text or call Vossome to make sure the team can follow up.")
        messages.success(request, "Your request has been received. A real human on the Vossome team will review it and follow up. No appointment has been booked.")
        request.session["contact_submitted"] = True
        return redirect("contact")
    return render(
        request,
        "contact.html",
        _contact_context(request, form, recaptcha_config),
    )
