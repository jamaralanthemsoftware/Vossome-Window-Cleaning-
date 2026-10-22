from django.db import migrations


# Add presentation markers to the current CMS copy without replacing anything an
# editor has changed. Markers live on the heading so moving its HTML moves its style.
HEADINGS = (
    ("“Wait... are the windows open?”", "intro"),
    ("Choose your own window cleaning adventure", "adventure"),
    ("Transparent pricing for transparent windows", "transparent"),
    ("This Is the Vossome Way", "way"),
    ("Ready for a brighter view?", "ready"),
)


def mark_existing_chapters(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    for service in Service.objects.filter(slug="window-cleaning"):
        body = service.body
        for heading, kind in HEADINGS:
            body = body.replace(
                f"<h2>{heading}</h2>",
                f'<h2 data-window-chapter="{kind}">{heading}</h2>',
                1,
            )
        if body != service.body:
            Service.objects.filter(pk=service.pk).update(body=body)


class Migration(migrations.Migration):
    dependencies = [("core", "0020_window_cleaning_invalid_cta")]
    operations = [migrations.RunPython(mark_existing_chapters, migrations.RunPython.noop)]