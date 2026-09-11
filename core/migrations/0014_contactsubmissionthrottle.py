from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0013_lead_anthem_delivery")]

    operations = [
        migrations.CreateModel(
            name="ContactSubmissionThrottle",
            fields=[
                (
                    "fingerprint",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
                ("window_started_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
            ],
        ),
    ]