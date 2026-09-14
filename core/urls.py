from django.urls import path

from .views import (
    PageDetailView,
    ServiceDetailView,
    about,
    contact,
    faq,
    healthz,
    home,
    robots_txt,
    services,
    commercial,
)

urlpatterns = [
    path("", home, name="home"),
    path("healthz/", healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("about/", about, name="about"),
    path("contact/", contact, name="contact"),
    path("faq/", faq, name="faq"),
    path("services/", services, name="services"),
    path(
        "commercial-window-cleaning/",
        commercial,
        name="commercial",
    ),
    path("services/<slug:slug>/", ServiceDetailView.as_view(), name="service-detail"),
    path("<slug:slug>/", PageDetailView.as_view(), name="page-detail"),
]
