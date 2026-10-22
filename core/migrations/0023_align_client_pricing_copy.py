"""Apply the approved pricing copy without replacing unrelated editor content."""
import re
from django.db import migrations


WINDOW_SCRIPT = "Standard pricing on standard windows is $100 to come out + $10 per window. That includes insides, outsides, screens, sills, and tracks; the whole window"
WINDOW_SUPPORT = "<p>A ballpark count is all we need—there’s no need for concrete numbers just to get on the schedule. An estimate just helps us plan our day and gives you an idea of the pricing.</p><p>On the day of the appointment, we’ll take a quick lap, count everything up, and review expectations and the exact price with you. Once you give us the okay, we’ll get started.</p>"


def align_copy(apps, schema_editor):
    for model_name in ("Service", "Page", "FAQ", "SiteSettings"):
        Model = apps.get_model("core", model_name)
        fields = [field for field in Model._meta.fields if field.get_internal_type() in ("TextField", "CharField") and field.name not in ("slug", "email", "phone")]
        for obj in Model.objects.all():
            changes = {}
            for field in fields:
                original = getattr(obj, field.name)
                if not isinstance(original, str):
                    continue
                value = re.sub(r"\bfree quote\b", "quote", original, flags=re.I)
                if model_name == "Service" and obj.slug == "window-cleaning":
                    if field.name == "body":
                        value = re.sub(
                            r'<section\b[^>]*class="window-pricing"[^>]*>.*?</section>',
                            '<section class="window-pricing" data-window-chapter="pricing" aria-labelledby="window-pricing-heading"><h2 id="window-pricing-heading">MEANWHILE... THE NUMBERS!</h2><p>' + WINDOW_SCRIPT + "</p>" + WINDOW_SUPPORT + "</section>",
                            value, flags=re.S,
                        )
                        value = value.replace(" Prefer to keep the visit outdoors? Exterior-only is absolutely fine.", "")
                        value = re.sub(r"<p>Only want the exteriors\?.*?</p>", "", value, flags=re.S)
                        value = re.sub(r"<p>Exterior-only window cleaning:.*?</p>", "", value, flags=re.S)
                        value = re.sub(r"<p>Full window cleaning:.*?</p>", "<p>We confirm the scope and exact price with you before starting.</p>", value, flags=re.S)
                    elif "exterior only" in value.lower() or "exterior-only" in value.lower():
                        value = "Residential window cleaning in St. Charles: $100 to come out + $10 per standard window, including insides, outsides, screens, sills, and tracks."
                if value != original:
                    changes[field.name] = value
            if changes:
                Model.objects.filter(pk=obj.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("core", "0022_pricing_first_inquiries")]
    operations = [migrations.RunPython(align_copy, migrations.RunPython.noop)]
