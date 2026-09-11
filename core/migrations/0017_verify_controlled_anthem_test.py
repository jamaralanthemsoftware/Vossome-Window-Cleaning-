from django.db import migrations


SOURCE = "controlled-anthem-production-test"
MESSAGE = (
    "CONTROLLED ANTHEM INTEGRATION TEST — organization 396 verification. "
    "Please do not contact; no service is requested."
)


def verify_controlled_anthem_test(apps, schema_editor):
    Lead = apps.get_model("core", "Lead")
    matches = Lead.objects.filter(source=SOURCE, message=MESSAGE)
    if matches.count() != 1:
        raise RuntimeError("Expected exactly one controlled Anthem test lead.")
    lead = matches.get()
    if lead.anthem_delivery_status != "confirmed":
        raise RuntimeError("Controlled Anthem test lead is not confirmed.")


class Migration(migrations.Migration):
    dependencies = [("core", "0016_enable_anthem_integration")]

    operations = [
        migrations.RunPython(
            verify_controlled_anthem_test,
            migrations.RunPython.noop,
        ),
    ]