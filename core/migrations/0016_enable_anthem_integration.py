from django.db import migrations


def enable_anthem_integration(apps, schema_editor):
    AnthemIntegration = apps.get_model("core", "AnthemIntegration")
    AnthemIntegration.objects.filter(singleton_key="default").update(is_enabled=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0015_anthemintegration")]

    operations = [
        migrations.RunPython(
            enable_anthem_integration,
            migrations.RunPython.noop,
        ),
    ]