from django.db import migrations


SERVICE_FAQS = [
    (
        "What is included in Vossome window cleaning?",
        "We clean the agreed interior, exterior, or both sides of the glass using the right "
        "tools for the windows and access involved. We confirm details such as screens, tracks, "
        "and hard-to-reach windows when preparing your quote so you know exactly what is included.",
    ),
    (
        "How often should I have my windows professionally cleaned?",
        "Many homes benefit from professional window cleaning once or twice a year, while "
        "storefronts and high-traffic businesses may need service more often. Pollen, nearby "
        "trees, weather, and the look you want can all affect the best schedule.",
    ),
    (
        "What surfaces can Vossome pressure wash?",
        "Pressure washing can refresh many exterior surfaces, including suitable siding, "
        "walkways, driveways, and other outdoor areas. We review the material and condition "
        "first, then choose an appropriate cleaning approach instead of treating every surface "
        "the same.",
    ),
    (
        "Is pressure washing safe for my property?",
        "It is when the cleaning method is matched to the surface and used carefully. We assess "
        "the work area, use sensible pressure, and pay attention to nearby windows, doors, "
        "fixtures, and landscaping before and during the job.",
    ),
    (
        "How can I tell when my gutters need cleaning?",
        "Overflowing water, visible leaves, sagging debris, staining below the gutter line, or "
        "plants growing in the gutters are common warning signs. Cleaning before a blockage "
        "causes overflow helps rainwater keep moving where it should.",
    ),
    (
        "How often should gutters be professionally cleaned?",
        "Most properties should check their gutters at least once or twice a year, especially "
        "after heavy leaf fall. Homes with overhanging trees may need more frequent service. "
        "We can recommend a practical schedule based on what surrounds your property.",
    ),
    (
        "Can concrete patio cleaning remove every stain?",
        "Professional cleaning can dramatically improve dirt, organic buildup, and many weather "
        "marks, but some deep rust, oil, paint, or permanent discoloration may not disappear "
        "completely. We set realistic expectations after seeing the patio's condition.",
    ),
    (
        "When can I use my concrete patio after cleaning?",
        "You can usually walk on the patio once the surface is no longer slippery, but full "
        "drying time depends on the weather, shade, and drainage. We will let you know what to "
        "expect and when it is sensible to replace furniture.",
    ),
]


def add_service_faqs(apps, schema_editor):
    FAQ = apps.get_model("core", "FAQ")
    for order, (question, answer) in enumerate(SERVICE_FAQS, start=10):
        FAQ.objects.update_or_create(
            question=question,
            defaults={
                "answer": answer,
                "is_published": True,
                "display_order": order,
            },
        )


def remove_service_faqs(apps, schema_editor):
    FAQ = apps.get_model("core", "FAQ")
    FAQ.objects.filter(question__in=[question for question, _ in SERVICE_FAQS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0004_seed_vossome_content")]

    operations = [migrations.RunPython(add_service_faqs, remove_service_faqs)]