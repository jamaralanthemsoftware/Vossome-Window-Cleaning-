from django.contrib import admin
from django.shortcuts import redirect

from .models import DownloadableAsset, FAQ, GoogleIntegration, Lead, Page, Service, SiteSettings


@admin.register(GoogleIntegration)
class GoogleIntegrationAdmin(admin.ModelAdmin):
    list_display = ["connected_email", "analytics_property_id", "gsc_verified_at", "updated_at"]
    readonly_fields = [field.name for field in GoogleIntegration._meta.fields if field.name != "refresh_token_encrypted"]
    exclude = ["refresh_token_encrypted"]

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect("google-integration-dashboard")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Identity", {"fields": ["site_name", "tagline"]}),
        ("Contact", {"fields": ["contact_email", "contact_phone", "address"]}),
        (
            "Search and analytics",
            {
                "fields": [
                    "default_meta_description",
                    "default_open_graph_title",
                    "default_open_graph_description",
                    "default_open_graph_image",
                    "analytics_measurement_id",
                    "search_console_verification_token",
                ]
            },
        ),
        ("Legal", {"fields": ["footer_disclaimer"]}),
    ]

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "is_published", "show_in_navigation", "updated_at"]
    list_filter = ["is_published", "show_in_navigation"]
    search_fields = ["title", "summary", "body"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["word_count"]
    fieldsets = [
        ("Content", {"fields": ["title", "slug", "summary", "body", "word_count"]}),
        (
            "Search and social sharing",
            {
                "fields": [
                    "meta_title",
                    "meta_description",
                    "open_graph_title",
                    "open_graph_description",
                    "open_graph_image",
                ]
            },
        ),
        (
            "Publishing",
            {"fields": ["is_published", "published_at", "show_in_navigation", "navigation_order"]},
        ),
    ]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "is_published", "display_order", "updated_at"]
    list_filter = ["is_published"]
    search_fields = ["title", "summary", "body"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["word_count"]
    fieldsets = [
        ("Content", {"fields": ["title", "slug", "summary", "body", "word_count"]}),
        (
            "Search and social sharing",
            {
                "fields": [
                    "meta_title",
                    "meta_description",
                    "open_graph_title",
                    "open_graph_description",
                    "open_graph_image",
                ]
            },
        ),
        (
            "Call to action",
            {"fields": ["call_to_action_label", "call_to_action_url"]},
        ),
        (
            "Publishing",
            {"fields": ["is_published", "published_at", "display_order"]},
        ),
    ]


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ["question", "is_published", "display_order", "updated_at"]
    list_filter = ["is_published"]
    list_editable = ["is_published", "display_order"]
    search_fields = ["question", "answer"]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "status", "source", "created_at"]
    list_filter = ["status", "consent_to_contact", "created_at"]
    search_fields = ["name", "email", "phone", "message"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(DownloadableAsset)
class DownloadableAssetAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "is_published", "updated_at"]
    list_filter = ["is_published"]
    prepopulated_fields = {"slug": ("title",)}
