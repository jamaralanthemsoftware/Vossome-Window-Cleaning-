import re

import uuid
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SiteSettings(TimeStampedModel):
    site_name = models.CharField(max_length=120, default="Client Website")
    tagline = models.CharField(max_length=180, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    default_meta_description = models.CharField(max_length=300, blank=True)
    default_open_graph_title = models.CharField(max_length=70, blank=True)
    default_open_graph_description = models.CharField(max_length=200, blank=True)
    default_open_graph_image = models.FileField(
        upload_to="open-graph/%Y/%m/",
        blank=True,
    )
    footer_disclaimer = models.TextField(blank=True)
    analytics_measurement_id = models.CharField(
        max_length=50, blank=True,
        validators=[RegexValidator(r"^$|^G-[A-Za-z0-9]+$", "Enter a valid GA4 measurement ID.")],
    )
    search_console_verification_token = models.CharField(
        max_length=255, blank=True,
        validators=[RegexValidator(r"^$|^[A-Za-z0-9_-]+$", "Enter a valid Google Search Console verification token.")],
    )

    @property
    def valid_analytics_measurement_id(self):
        return bool(self.analytics_measurement_id and re.fullmatch(r"G-[A-Za-z0-9]+", self.analytics_measurement_id))

    class Meta:
        verbose_name_plural = "site settings"

    def clean(self):
        if self.pk is None and SiteSettings.objects.exists():
            raise ValidationError("Only one SiteSettings record is allowed.")

    def __str__(self):
        return self.site_name


class GoogleIntegration(TimeStampedModel):
    singleton_key = models.CharField(max_length=20, unique=True, default="default", editable=False)
    google_subject = models.CharField(max_length=255, blank=True)
    connected_email = models.EmailField(blank=True)
    email_verified = models.BooleanField(default=False)
    refresh_token_encrypted = models.TextField(blank=True)
    analytics_account_id = models.CharField(max_length=120, blank=True)
    analytics_property_id = models.CharField(max_length=120, blank=True)
    analytics_data_stream_id = models.CharField(max_length=120, blank=True)
    analytics_measurement_id = models.CharField(
        max_length=50, blank=True,
        validators=[RegexValidator(r"^$|^G-[A-Za-z0-9]+$", "Enter a valid GA4 measurement ID.")],
    )
    gsc_verification_token = models.CharField(max_length=255, blank=True)
    gsc_verified_at = models.DateTimeField(null=True, blank=True)
    gsc_property_added_at = models.DateTimeField(null=True, blank=True)
    gsc_sitemap_submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Google integration"
        verbose_name_plural = "Google integration"

    def clean(self):
        if self.pk is None and GoogleIntegration.objects.exists():
            raise ValidationError("Only one GoogleIntegration record is allowed.")

    def __str__(self):
        return self.connected_email or "Google integration"


def validate_anthem_webhook_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "live.anthemcrm.com"
        or parsed.port not in (None, 443)
        or parsed.path
        != "/api/v1/organization/396/gravity-forms-webhook/"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValidationError(
            "Enter the HTTPS Anthem webhook for organization 396."
        )


class AnthemIntegration(TimeStampedModel):
    singleton_key = models.CharField(
        max_length=20,
        unique=True,
        default="default",
        editable=False,
    )
    webhook_url = models.URLField(
        max_length=500,
        validators=[validate_anthem_webhook_url],
        help_text=(
            "The organization 396 Gravity Forms webhook on live.anthemcrm.com."
        ),
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text=(
            "Enable only after deployment configuration is ready and a controlled "
            "test submission has been approved."
        ),
    )

    class Meta:
        verbose_name = "Anthem CRM integration"
        verbose_name_plural = "Anthem CRM integration"

    def clean(self):
        if self.pk is None and AnthemIntegration.objects.exists():
            raise ValidationError("Only one Anthem CRM integration is allowed.")

    def __str__(self):
        return "Anthem CRM integration"


class RecaptchaIntegration(TimeStampedModel):
    singleton_key = models.CharField(
        max_length=20,
        unique=True,
        default="default",
        editable=False,
    )
    site_key = models.CharField(
        max_length=255,
        help_text="The public Google reCAPTCHA v3 site key. This is safe to expose.",
    )
    minimum_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.5,
        help_text="Reject scores below this value. Google recommends starting at 0.5.",
    )
    allowed_hostnames = models.TextField(
        default="vossomewindowcleaning.com\nwww.vossomewindowcleaning.com",
        help_text="One hostname per line, without https:// or a path.",
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text=(
            "Enable invisible reCAPTCHA on the public contact form. The encrypted "
            "secret key must also be configured in the deployment."
        ),
    )

    class Meta:
        verbose_name = "reCAPTCHA integration"
        verbose_name_plural = "reCAPTCHA integration"

    @property
    def normalized_hostnames(self):
        return {
            hostname.strip().lower()
            for hostname in self.allowed_hostnames.replace(",", "\n").splitlines()
            if hostname.strip()
        }

    def clean(self):
        if self.pk is None and RecaptchaIntegration.objects.exists():
            raise ValidationError("Only one reCAPTCHA integration is allowed.")
        if not 0 <= self.minimum_score <= 1:
            raise ValidationError(
                {"minimum_score": "Enter a score between 0 and 1."}
            )
        invalid_hostnames = [
            hostname
            for hostname in self.normalized_hostnames
            if (
                not re.fullmatch(
                    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                    hostname,
                )
                or ":" in hostname
            )
        ]
        if invalid_hostnames:
            raise ValidationError(
                {"allowed_hostnames": "Enter hostnames only, one per line."}
            )
        if self.is_enabled and (not self.site_key or not self.normalized_hostnames):
            raise ValidationError(
                "Enabled reCAPTCHA requires a site key and at least one hostname."
            )

    def __str__(self):
        return "Google reCAPTCHA v3"


class PublishableModel(TimeStampedModel):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True)
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)
    open_graph_title = models.CharField(max_length=70, blank=True)
    open_graph_description = models.CharField(max_length=200, blank=True)
    open_graph_image = models.FileField(
        upload_to="open-graph/%Y/%m/",
        blank=True,
    )
    is_published = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

    @property
    def seo_title(self):
        return self.meta_title or self.title

    @property
    def seo_description(self):
        return self.meta_description or self.summary

    @property
    def resolved_open_graph_title(self):
        return self.open_graph_title or self.seo_title

    @property
    def resolved_open_graph_description(self):
        return self.open_graph_description or self.seo_description

    @property
    def word_count(self):
        return len(strip_tags(self.body).split())

    def _populate_metadata_defaults(self):
        plain_body = " ".join(strip_tags(self.body).split())
        description_source = self.summary or plain_body
        if not self.meta_title:
            self.meta_title = Truncator(self.title).chars(70)
        if not self.meta_description and description_source:
            self.meta_description = Truncator(description_source).chars(160)
        if not self.open_graph_title:
            self.open_graph_title = self.meta_title
        if not self.open_graph_description and description_source:
            self.open_graph_description = Truncator(description_source).chars(200)

    def clean(self):
        super().clean()
        self._populate_metadata_defaults()
        if self.is_published and not 650 <= self.word_count <= 900:
            raise ValidationError(
                {
                    "body": (
                        "Published content pages should be approximately 750 words. "
                        f"This page currently has {self.word_count} words; use 650–900."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self._populate_metadata_defaults()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Page(PublishableModel):
    show_in_navigation = models.BooleanField(default=False)
    navigation_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["navigation_order", "title"]

    def get_absolute_url(self):
        return reverse("page-detail", kwargs={"slug": self.slug})


class Service(PublishableModel):
    call_to_action_label = models.CharField(max_length=80, blank=True)
    call_to_action_url = models.URLField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "title"]

    def get_absolute_url(self):
        return reverse("service-detail", kwargs={"slug": self.slug})


class FAQ(TimeStampedModel):
    question = models.CharField(max_length=240)
    answer = models.TextField()
    is_published = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "question"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class Lead(TimeStampedModel):
    class AnthemDeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ATTEMPTING = "attempting", "Attempting"
        CONFIRMED = "confirmed", "Confirmed"
        NEEDS_REVIEW = "needs_review", "Needs review"
        CONFIGURATION_ERROR = "configuration_error", "Configuration error"

    class ServiceInterest(models.TextChoices):
        WINDOW_CLEANING = "window-cleaning", "Window Cleaning"
        PRESSURE_WASHING = "pressure-washing", "Pressure Washing"
        GUTTER_CLEANING = "gutter-cleaning", "Gutter Cleaning"
        CONCRETE_PATIO_CLEANING = "concrete-patio-cleaning", "Concrete Patio Cleaning"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CLOSED = "closed", "Closed"

    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    service_interest = models.CharField(
        max_length=40,
        choices=ServiceInterest.choices,
        blank=True,
    )
    message = models.TextField()
    source = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    consent_to_contact = models.BooleanField(default=False)
    submission_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    anthem_delivery_status = models.CharField(
        max_length=32,
        choices=AnthemDeliveryStatus.choices,
        default=AnthemDeliveryStatus.PENDING,
    )
    anthem_attempted_at = models.DateTimeField(blank=True, null=True)
    anthem_http_status = models.PositiveSmallIntegerField(blank=True, null=True)
    anthem_error_summary = models.CharField(max_length=240, blank=True)
    anthem_record_identifier = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.full_name} ({self.email})"


class ContactSubmissionThrottle(models.Model):
    fingerprint = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)


class DownloadableAsset(TimeStampedModel):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="downloads/%Y/%m/")
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return self.title
