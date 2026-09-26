from django.db import migrations


def clear_invalid_relative_cta(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    Service.objects.filter(
        slug="window-cleaning", call_to_action_url="/contact/"
    ).update(call_to_action_url="")


class Migration(migrations.Migration):
    dependencies = [("core", "0019_window_cleaning_client_copy")]
    operations = [migrations.RunPython(clear_invalid_relative_cta, migrations.RunPython.noop)]