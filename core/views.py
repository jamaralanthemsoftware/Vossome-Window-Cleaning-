import logging
import uuid
from datetime import timedelta
from hashlib import sha256
from ipaddress import ip_address

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.generic import DetailView

from .anthem import deliver_lead_to_anthem
from .forms import LeadForm
from .models import ContactSubmissionThrottle, FAQ, Page, Service


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


def send_lead_notification(lead):
    if not settings.LEAD_NOTIFICATION_EMAIL:
        return

    consent = "Yes" if lead.consent_to_contact else "No"
    body = "\n".join(
        [
            "A new contact-form lead was submitted on the Vossome website.",
            "",
            f"First name: {lead.first_name}",
            f"Last name: {lead.last_name}",
            f"Email: {lead.email}",
            f"Phone: {lead.phone or 'Not provided'}",
            f"Service: {lead.get_service_interest_display() or 'Not specified'}",
            f"Consent to contact: {consent}",
            f"Source: {lead.source or 'website'}",
            "",
            "Message:",
            lead.message,
        ]
    )
    message = EmailMessage(
        subject=f"New Vossome {lead.get_service_interest_display() or 'website'} lead: {lead.full_name}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.LEAD_NOTIFICATION_EMAIL],
        reply_to=[lead.email],
    )
    try:
        message.send(fail_silently=False)
    except Exception:
        logger.exception("Lead notification email failed for lead_id=%s", lead.pk)


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
    submission_token = _contact_submission_token(request)
    form = LeadForm(
        request.POST or None,
        initial={"submission_token": submission_token},
        expected_submission_token=submission_token,
    )
    if request.method == "POST" and _contact_rate_limited(request):
        messages.error(
            request,
            "Too many requests were submitted. Please call or text us instead.",
        )
        return render(
            request,
            "contact.html",
            {"form": form, "contact_submitted": False},
            status=429,
        )
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        lead.source = request.POST.get("source", "website")[:120]
        lead.submission_token = form.cleaned_data["submission_token"]
        try:
            with transaction.atomic():
                lead.save()
        except IntegrityError:
            messages.success(request, "Thank you. Your message has been received.")
            request.session["contact_submitted"] = True
            request.session.pop(CONTACT_SUBMISSION_TOKEN_KEY, None)
            return redirect("contact")
        request.session.pop(CONTACT_SUBMISSION_TOKEN_KEY, None)
        deliver_lead_to_anthem(lead.pk)
        send_lead_notification(lead)
        messages.success(request, "Thank you. Your message has been received.")
        request.session["contact_submitted"] = True
        return redirect("contact")
    return render(request, "contact.html", {"form": form, "contact_submitted": request.session.pop("contact_submitted", False)})
