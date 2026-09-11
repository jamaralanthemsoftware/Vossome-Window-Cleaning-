from django.db import migrations, models

import core.models


def create_anthem_integration(apps, schema_editor):
    AnthemIntegration = apps.get_model("core", "AnthemIntegration")
    AnthemIntegration.objects.get_or_create(
        singleton_key="default",
        defaults={
            "webhook_url": (
                "https://live.anthemcrm.com/api/v1/organization/396/"
                "gravity-forms-webhook/"
            ),
            "is_enabled": False,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0014_contactsubmissionthrottle")]

    operations = [
        migrations.CreateModel(
            name="AnthemIntegration",
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
                    "webhook_url",
                    models.URLField(
                        help_text=(
                            "The organization 396 Gravity Forms webhook on "
                            "live.anthemcrm.com."
                        ),
                        max_length=500,
                        validators=[core.models.validate_anthem_webhook_url],
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Enable only after deployment configuration is ready "
                            "and a controlled test submission has been approved."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Anthem CRM integration",
                "verbose_name_plural": "Anthem CRM integration",
            },
        ),
        migrations.RunPython(
            create_anthem_integration,
            migrations.RunPython.noop,
        ),
    ]