from urllib.parse import urlencode

from django.conf import settings
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters


@never_cache
def admin_sso_login(request):
    if not settings.ENABLE_GOOGLE_ADMIN_SSO:
        return admin.site.login(request)

    next_url = request.GET.get("next") or reverse("admin:index")
    query = urlencode({"process": "login", "next": next_url})
    return redirect(f"{reverse('google_login')}?{query}")


@sensitive_post_parameters()
@never_cache
def emergency_admin_login(request):
    """Local-password entry point reserved for the break-glass superuser."""
    return admin.site.login(request)
