from django.db import migrations


WINDOW_BODY = """
<h2>“Wait... are the windows open?”</h2>
<p>We hear some version of that all the time. Once the film, fingerprints, and grime are gone, the glass stops calling attention to itself altogether—and the view takes over. That little double take never gets old.</p>
<p>Vossome cleans residential windows in St. Charles and nearby communities. We’re a family business with three generations of window-cleaning experience, but we’re really in the Happy Client Business—which means the experience matters as much as the view.</p>
<p>Need windows cleaned at work, too? Our commercial crew at <a href="/commercial-window-cleaning/">Brighter View Window Cleaning</a> handles storefronts, offices, churches, dealerships, medical laboratories, and the occasional secret volcano lair.</p>
<section class="window-pricing" aria-labelledby="window-pricing-heading">
  <h2 id="window-pricing-heading">MEANWHILE... THE NUMBERS!</h2>
  <div class="window-pricing-grid">
    <div><h3>Full window cleaning</h3><p><strong>$100 visit + $10 per window</strong></p></div>
    <div><h3>Exterior only</h3><p><strong>$100 visit + $7 per window</strong></p></div>
  </div>
  <p>Standard pricing for standard windows. Final quote confirmed before work begins.</p>
</section>
<h2>Choose your own window cleaning adventure</h2>
<p>Want the whole job done? Our default setting is to clean the insides, outsides, screens, sills, and tracks; the whole window. Have atypical windows? Text over some photos and let’s talk.</p>
<p>Only want the exteriors? That works too. Tell us what you have in mind, and we’ll give you a clear quote before work begins. If a window needs special access or extra attention, just let us know.</p>
<h2>Transparent pricing for transparent windows</h2>
<p>Full window cleaning: Standard windows run $100 to come out, plus $10 per window. That includes insides, outsides, screens, sills, and tracks—the whole window.</p>
<p>Exterior-only window cleaning: The same $100 to come out, plus $7 per window.</p>
<p>Older windows, storm windows, difficult access, or anything requiring a spell of levitation may cost more. Send us some photos, and we’ll talk it through before quoting. We’ll confirm the scope and price before we ever touch glass so there are no surprises!</p>
<h2>This Is the Vossome Way</h2>
<p>We’ll communicate clearly, treat your home with care, and pay attention to the details you’ll notice when the sun hits the glass. Having us in your home should feel comfortable and straightforward. A lot of clients have trusted us for years to be there even when they are not, and that’s an honor and a half. Prefer to keep the visit outdoors? Exterior-only is absolutely fine.</p>
<p>Clean windows pair especially well with a house wash, concrete cleaning, gutter cleaning, or a nice Sauvignon blanc while you enjoy the brighter view. Share your honey-do list, and we’ll help you plan the visit.</p>
<h2>Ready for a brighter view?</h2>
<p>Text us at <a href="sms:+13147751080">(314) 775-1080</a>. A name, address, and an approximate window count are a great start. We’ll take it from there.</p>
"""


def apply_copy(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    Service.objects.filter(slug="window-cleaning").update(
        summary="Residential window cleaning in St. Charles and nearby communities, with a clear quote and a view worth a double take.",
        body=WINDOW_BODY,
        meta_description="St. Charles residential window cleaning: $100 visit + $10 per window for full service, or $7 per window for exterior only. Final quote before work begins.",
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0018_lead_multiple_services_reply")]
    operations = [migrations.RunPython(apply_copy, migrations.RunPython.noop)]