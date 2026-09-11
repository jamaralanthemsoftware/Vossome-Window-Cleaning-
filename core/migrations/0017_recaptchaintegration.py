import os

from django.db import migrations, models


def create_recaptcha_integration(apps, schema_editor):
    RecaptchaIntegration = apps.get_model("core", "RecaptchaIntegration")
    site_key = os.getenv("RECAPTCHA_SITE_KEY", "")
    RecaptchaIntegration.objects.get_or_create(
        singleton_key="default",
        defaults={
            "site_key": site_key,
            "minimum_score": 0.5,
            "allowed_hostnames": (
                "vossomewindowcleaning.com\n"
                "www.vossomewindowcleaning.com"
            ),
            "is_enabled": bool(site_key),
        },
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0016_enable_anthem_integration")]

    operations = [
        migrations.CreateModel(
            name="RecaptchaIntegration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "singleton_key",
                    models.CharField(
                        default="default",
                        editable=False,
                        max_length=20,
                        unique=True,
                    ),
                ),
                (
                    "site_key",
                    models.CharField(
                        help_text=(
                            "The public Google reCAPTCHA v3 site key. "
                            "This is safe to expose."
                        ),
                        max_length=255,
                    ),
                ),
                (
                    "minimum_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=0.5,
                        help_text=(
                            "Reject scores below this value. Google recommends "
                            "starting at 0.5."
                        ),
                        max_digits=3,
                    ),
                ),
                (
                    "allowed_hostnames",
                    models.TextField(
                        default=(
                            "vossomewindowcleaning.com\n"
                            "www.vossomewindowcleaning.com"
                        ),
                        help_text=(
                            "One hostname per line, without https:// or a path."
                        ),
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Enable invisible reCAPTCHA on the public contact "
                            "form. The encrypted secret key must also be "
                            "configured in the deployment."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "reCAPTCHA integration",
                "verbose_name_plural": "reCAPTCHA integration",
            },
        ),
        migrations.RunPython(
            create_recaptcha_integration,
            migrations.RunPython.noop,
        ),
    ]