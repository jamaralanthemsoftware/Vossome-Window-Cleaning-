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
        print(
            "Controlled Anthem test audit: "
            f"expected one lead, found {matches.count()}."
        )
        return
    lead = matches.get()
    print(
        "Controlled Anthem test audit: "
        f"status={lead.anthem_delivery_status}; "
        f"http_status={lead.anthem_http_status}; "
        f"error={lead.anthem_error_summary or 'none'}."
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0016_enable_anthem_integration")]

    operations = [
        migrations.RunPython(
            verify_controlled_anthem_test,
            migrations.RunPython.noop,
        ),
    ]