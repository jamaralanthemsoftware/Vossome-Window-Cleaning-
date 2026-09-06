import logging

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

logger = logging.getLogger("security.authentication")


@receiver(user_logged_in)
def log_staff_login(sender, request, user, **kwargs):
    if user.is_staff:
        logger.info("Administrator login succeeded for user_id=%s", user.pk)


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    username = credentials.get("username") or credentials.get("email") or "unknown"
    logger.warning("Authentication failed for identifier=%s", username)
