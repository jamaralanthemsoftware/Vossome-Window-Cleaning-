import logging

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden

logger = logging.getLogger("security.authentication")


def deny_social_login(message: str) -> None:
    logger.warning("Google administrator sign-in denied: %s", message)
    raise ImmediateHttpResponse(
        HttpResponseForbidden(
            "This Google account is not authorized for website administration."
        )
    )


class AdminSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Allow Google login only for explicitly approved, existing staff users."""

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        email = (sociallogin.user.email or "").strip().casefold()
        if not email or email not in settings.ADMIN_GOOGLE_ALLOWED_EMAILS:
            deny_social_login("email is not on the administrator allowlist")

        user_model = get_user_model()
        try:
            user = user_model.objects.get(
                email__iexact=email,
                is_active=True,
                is_staff=True,
            )
        except user_model.DoesNotExist:
            deny_social_login("no matching active staff user exists")
        except user_model.MultipleObjectsReturned:
            deny_social_login("multiple users share the approved email address")

        if not sociallogin.is_existing:
            sociallogin.connect(request, user)
