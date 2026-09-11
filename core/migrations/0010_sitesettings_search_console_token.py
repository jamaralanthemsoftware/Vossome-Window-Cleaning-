from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_measurement_id_validators"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="search_console_verification_token",
            field=models.CharField(
                blank=True,
                max_length=255,
                validators=[
                    RegexValidator(
                        "^$|^[A-Za-z0-9_-]+$",
                        "Enter a valid Google Search Console verification token.",
                    )
                ],
            ),
        ),
    ]