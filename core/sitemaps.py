from django.contrib.sitemaps import Sitemap

from .models import Page, Service


class PublishedContentSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def lastmod(self, obj):
        return obj.updated_at


class PageSitemap(PublishedContentSitemap):
    def items(self):
        return Page.objects.filter(is_published=True)


class ServiceSitemap(PublishedContentSitemap):
    def items(self):
        return Service.objects.filter(is_published=True)
