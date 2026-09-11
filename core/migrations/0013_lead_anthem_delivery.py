import uuid

from django.db import migrations, models


def populate_submission_tokens(apps, schema_editor):
    Lead = apps.get_model("core", "Lead")
    for lead in Lead.objects.filter(submission_token__isnull=True).iterator():
        lead.submission_token = uuid.uuid4()
        lead.save(update_fields=["submission_token"])


class Migration(migrations.Migration):
    dependencies = [("core", "0012_lead_contact_fields")]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="submission_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(
            populate_submission_tokens,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="lead",
            name="submission_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="anthem_delivery_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("attempting", "Attempting"),
                    ("confirmed", "Confirmed"),
                    ("needs_review", "Needs review"),
                    ("configuration_error", "Configuration error"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="anthem_attempted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="anthem_http_status",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="anthem_error_summary",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="lead",
            name="anthem_record_identifier",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]