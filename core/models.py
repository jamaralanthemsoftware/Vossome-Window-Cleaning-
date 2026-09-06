from django.core.exceptions import ValidationError
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
    analytics_measurement_id = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = "site settings"

    def clean(self):
        if self.pk is None and SiteSettings.objects.exists():
            raise ValidationError("Only one SiteSettings record is allowed.")

    def __str__(self):
        return self.site_name


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
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    message = models.TextField()
    source = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    consent_to_contact = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.email})"


class DownloadableAsset(TimeStampedModel):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="downloads/%Y/%m/")
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return self.title
