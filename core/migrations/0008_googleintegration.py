from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_reposition_about_page")]
    operations = [
        migrations.CreateModel(
            name="GoogleIntegration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("connected_email", models.EmailField(blank=True, max_length=254)),
                ("refresh_token_encrypted", models.TextField(blank=True)),
                ("analytics_account_id", models.CharField(blank=True, max_length=120)),
                ("analytics_property_id", models.CharField(blank=True, max_length=120)),
                ("analytics_data_stream_id", models.CharField(blank=True, max_length=120)),
                ("analytics_measurement_id", models.CharField(
                    blank=True, max_length=50,
                    validators=[RegexValidator(r"^$|^G-[A-Za-z0-9]+$", "Enter a valid GA4 measurement ID.")],
                )),
                ("gsc_verification_token", models.CharField(blank=True, max_length=255)),
                ("gsc_verified_at", models.DateTimeField(blank=True, null=True)),
                ("gsc_property_added_at", models.DateTimeField(blank=True, null=True)),
                ("gsc_sitemap_submitted_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"verbose_name": "Google integration", "verbose_name_plural": "Google integration"},
        )
    ]