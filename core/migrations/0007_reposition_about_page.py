from django.db import migrations


OLD_TITLE = "Meet Your Window Washer"
NEW_TITLE = "The Vossome Way"

OLD_SUMMARY = "Meet Matt Voss and the family story behind Vossome Window Cleaning."
NEW_SUMMARY = (
    "How a family story became a company standard built around happy clients."
)

OLD_BODY = """
    <p>Vossome Window Cleaning is a family-owned St. Charles business built around a simple
    idea: show up, do excellent work, and help people along the way. Owner Matt Voss grew up
    around window cleaning and started learning the craft as soon as he could hold a
    squeegee. That lifelong experience still shapes every job today.</p>
    <p>For Matt, the work has always been about more than glass. Vossome was created to give
    him the freedom to serve customers with care, run a business on his own terms, and give
    a portion of the company's gross earnings to charity. It is local service with a bigger
    why behind it.</p>
    <p>Customers can expect clear communication, respect for their property, and detail-minded
    work on windows, gutters, siding, driveways, and concrete patios. The goal is not to rush
    through a checklist. It is to leave the home or business looking noticeably brighter and
    to make the entire experience feel easy.</p>
    <p>That mix of professional skill, family values, and playful confidence is what makes the
    company Vossome. We take the work seriously without taking ourselves too seriously.
    Excellent service, honest relationships, and results worth talking about—that is how we
    do it #likeaVoss.</p>
    """

NEW_BODY = """
    <p>Vossome Window Cleaning began as a family business in St. Charles, shaped by Matt
    Voss's three generations of window-cleaning experience and the support of Julie and
    their family. That history matters because it established the care, personality, and
    local commitment behind the name. But the promise customers hire today belongs to
    Vossome as a company.</p>
    <p>We call it the Happy Client Business. It means clear communication before the work,
    dependable service when the day arrives, respect for every property, and a result we are
    proud to put the Vossome name on. Those standards are not tied to one person. They guide
    how the whole company answers questions, prepares for a job, completes the work, and
    follows through.</p>
    <p>Vossome cleans windows, refreshes exterior surfaces, and clears gutters throughout
    St. Charles and nearby St. Louis communities. Professional service does not have to feel
    stiff or impersonal. Customers can expect a friendly experience, honest expectations,
    and a team focused on making the process easy to recommend.</p>
    <p>Being local also means contributing locally. Supporting organizations like The
    Covering House remains part of the company's story and part of doing business
    #likeaVoss. The family provided the foundation; the Vossome standard is what carries the
    company forward.</p>
    """


def reposition_known_about_draft(apps, schema_editor):
    Page = apps.get_model("core", "Page")
    Page.objects.filter(slug="about", title=OLD_TITLE).update(
        title=NEW_TITLE,
        summary=NEW_SUMMARY,
        body=NEW_BODY,
        meta_title="About Vossome Window Cleaning | St. Charles, MO",
        meta_description=(
            "Learn how Vossome's family roots became a company-wide standard for "
            "clear communication, dependable service, and happy clients."
        ),
        open_graph_title="The Vossome Way",
        open_graph_description=NEW_SUMMARY,
    )


def restore_known_about_draft(apps, schema_editor):
    Page = apps.get_model("core", "Page")
    Page.objects.filter(slug="about", title=NEW_TITLE).update(
        title=OLD_TITLE,
        summary=OLD_SUMMARY,
        body=OLD_BODY,
        meta_title="Meet Your Window Washer | Vossome Window Cleaning",
        meta_description=OLD_SUMMARY,
        open_graph_title=OLD_TITLE,
        open_graph_description=OLD_SUMMARY,
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0006_expand_service_content")]

    operations = [
        migrations.RunPython(
            reposition_known_about_draft,
            restore_known_about_draft,
        )
    ]