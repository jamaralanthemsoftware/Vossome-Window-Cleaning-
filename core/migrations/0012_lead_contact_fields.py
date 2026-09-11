from django.db import migrations, models


def split_existing_names(apps, schema_editor):
    Lead = apps.get_model("core", "Lead")
    for lead in Lead.objects.all().iterator():
        first_name, separator, last_name = lead.name.strip().partition(" ")
        lead.first_name = first_name or "Unknown"
        lead.last_name = last_name if separator else ""
        lead.save(update_fields=["first_name", "last_name"])


class Migration(migrations.Migration):
    dependencies = [("core", "0011_google_identity_singleton")]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="first_name",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="lead",
            name="last_name",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="lead",
            name="service_interest",
            field=models.CharField(
                blank=True,
                choices=[
                    ("window-cleaning", "Window Cleaning"),
                    ("pressure-washing", "Pressure Washing"),
                    ("gutter-cleaning", "Gutter Cleaning"),
                    ("concrete-patio-cleaning", "Concrete Patio Cleaning"),
                ],
                max_length=40,
            ),
        ),
        migrations.RunPython(split_existing_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="lead",
            name="first_name",
            field=models.CharField(max_length=60),
        ),
        migrations.AlterField(
            model_name="lead",
            name="last_name",
            field=models.CharField(max_length=60),
        ),
        migrations.RemoveField(model_name="lead", name="name"),
    ]