from django.urls import path

from anthem_seo.views import managed_page
from .views import (
    BlogPostDetailView,
    PageDetailView,
    ServiceDetailView,
    about,
    blog_list,
    contact,
    faq,
    healthz,
    home,
    robots_txt,
    services,
    commercial,
    lead_photo,
)

urlpatterns = [
    path("", home, name="home"),
    path("healthz/", healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("about/", about, name="about"),
    path("contact/", contact, name="contact"),
    path("inquiries/photos/<int:pk>/", lead_photo, name="lead-photo"),
    path("faq/", faq, name="faq"),
    path("services/", services, name="services"),
    path("blog/", blog_list, name="blog"),
    path("blog/<slug:slug>/", BlogPostDetailView.as_view(), name="blog-detail"),
    path(
        "commercial-window-cleaning/",
        commercial,
        name="commercial",
    ),
    path("services/<slug:slug>/", ServiceDetailView.as_view(), name="service-detail"),
    path("<slug:slug>/", PageDetailView.as_view(), name="page-detail"),
    path("<path:seo_path>/", managed_page, name="anthem-managed-page"),
]
