from django.urls import path

from .google_views import (
    callback,
    connect,
    dashboard,
    disconnect,
    ga4_create_account,
    ga4_setup,
    gsc_token,
    gsc_verify,
    provisioning_callback,
)

urlpatterns = [
    path("", dashboard, name="google-integration-dashboard"),
    path("connect/", connect, name="google-integration-connect"),
    path("callback/", callback, name="google-integration-callback"),
    path(
        "provisioning-callback/<str:state>/",
        provisioning_callback,
        name="google-integration-provisioning-callback",
    ),
    path("disconnect/", disconnect, name="google-integration-disconnect"),
    path(
        "ga4/account/create/",
        ga4_create_account,
        name="google-integration-ga4-create-account",
    ),
    path("ga4/setup/", ga4_setup, name="google-integration-ga4-setup"),
    path("search-console/token/", gsc_token, name="google-integration-gsc-token"),
    path("search-console/verify/", gsc_verify, name="google-integration-gsc-verify"),
]