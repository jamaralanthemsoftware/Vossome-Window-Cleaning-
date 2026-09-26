from django.db import migrations, models


def backfill_services(apps, schema_editor):
    Lead = apps.get_model("core", "Lead")
    for lead in Lead.objects.exclude(service_interest="").iterator():
        lead.selected_services = [lead.service_interest]
        lead.save(update_fields=["selected_services"])


class Migration(migrations.Migration):
    dependencies = [("core", "0017_recaptchaintegration")]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="selected_services",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="lead",
            name="preferred_reply_method",
            field=models.CharField(
                blank=True, max_length=10,
                choices=[("text", "Text"), ("email", "Email"), ("call", "Call")],
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="deck_material",
            field=models.CharField(
                blank=True, max_length=12,
                choices=[("composite", "Composite"), ("wood", "Wood")],
            ),
        ),
        migrations.RunPython(backfill_services, migrations.RunPython.noop),
    ]