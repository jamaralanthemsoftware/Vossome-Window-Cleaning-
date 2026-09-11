from django.db import migrations, models


def validate_singleton(apps, schema_editor):
    model = apps.get_model("core", "GoogleIntegration")
    rows = list(model.objects.order_by("id"))
    if len(rows) > 1:
        raise RuntimeError(
            "Cannot add GoogleIntegration singleton constraint: "
            "multiple existing rows require explicit operator resolution."
        )
    if rows and not rows[0].singleton_key:
        model.objects.filter(pk=rows[0].pk).update(singleton_key="default")


class Migration(migrations.Migration):
    dependencies = [("core", "0010_sitesettings_search_console_token")]

    operations = [
        migrations.AddField(
            model_name="googleintegration",
            name="singleton_key",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="googleintegration",
            name="google_subject",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="googleintegration",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(validate_singleton, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="googleintegration",
            name="singleton_key",
            field=models.CharField(default="default", editable=False, max_length=20, unique=True),
        ),
    ]