from datetime import datetime, timezone as dt_timezone
from django.db import migrations


BLOG_PUBLISHED_DATES = {
    "professional-window-cleaning-cost-guide": datetime(
        2026, 10, 26, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "how-to-remove-hard-water-stains-from-windows": datetime(
        2026, 10, 23, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "pressure-washing-vs-soft-washing": datetime(
        2026, 10, 20, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "how-much-does-it-cost-to-pressure-wash-a-house": datetime(
        2026, 10, 17, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "what-happens-if-you-dont-clean-gutters": datetime(
        2026, 10, 14, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "gutter-cleaning-cost-per-foot": datetime(
        2026, 10, 11, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "how-to-clean-concrete-patio-without-pressure-washer": datetime(
        2026, 10, 8, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "can-pressure-washing-damage-concrete": datetime(
        2026, 10, 5, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "spring-exterior-home-maintenance-checklist": datetime(
        2026, 10, 2, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
    "fall-gutter-and-roof-maintenance-checklist": datetime(
        2026, 9, 29, 15, 0, 0, tzinfo=dt_timezone.utc
    ),
}


def set_blog_published_dates(apps, schema_editor):
    BlogPost = apps.get_model("core", "BlogPost")
    for slug, published_at in BLOG_PUBLISHED_DATES.items():
        BlogPost.objects.filter(slug=slug).update(published_at=published_at)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("core", "0034_seed_fall_maintenance_checklist_blog")]

    operations = [
        migrations.RunPython(set_blog_published_dates, noop_reverse),
    ]
