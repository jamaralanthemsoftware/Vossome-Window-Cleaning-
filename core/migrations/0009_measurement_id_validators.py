from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0008_googleintegration")]
    operations = [
        migrations.AlterField(
            model_name="googleintegration",
            name="analytics_measurement_id",
            field=models.CharField(
                blank=True, max_length=50,
                validators=[RegexValidator(r"^$|^G-[A-Za-z0-9]+$", "Enter a valid GA4 measurement ID.")],
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="analytics_measurement_id",
            field=models.CharField(
                blank=True, max_length=50,
                validators=[RegexValidator(r"^$|^G-[A-Za-z0-9]+$", "Enter a valid GA4 measurement ID.")],
            ),
        ),
    ]