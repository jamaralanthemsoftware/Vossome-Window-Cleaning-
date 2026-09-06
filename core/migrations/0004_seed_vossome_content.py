from django.db import migrations


def seed_vossome_content(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    Service = apps.get_model("core", "Service")
    FAQ = apps.get_model("core", "FAQ")

    SiteSettings.objects.update_or_create(
        pk=1,
        defaults={
            "site_name": "Vossome Window Cleaning",
            "tagline": "Clean windows. Big Voss energy.",
            "contact_phone": "(314) 775-1080",
            "address": "Serving St. Charles and nearby St. Louis communities",
            "default_meta_description": (
                "Family-owned window cleaning, pressure washing, gutter cleaning, "
                "and concrete patio cleaning in St. Charles, Missouri."
            ),
            "default_open_graph_title": "Vossome Window Cleaning | St. Charles, MO",
            "default_open_graph_description": (
                "Local window and exterior cleaning done #likeaVoss. "
                "Call (314) 775-1080 for a quote."
            ),
            "footer_disclaimer": (
                "Family-owned and proudly serving St. Charles and surrounding communities."
            ),
        },
    )

    services = [
        (
            "Window Cleaning",
            "window-cleaning",
            "Clear residential and commercial windows, carefully cleaned inside and out.",
            """
            <p>Clean windows change the feel of an entire property. Vossome Window Cleaning
            removes the film, fingerprints, pollen, dust, and everyday buildup that dulls the
            view and blocks natural light. We work carefully around your home or business and
            treat the surrounding surfaces with respect.</p>
            <p>Every project starts with a clear conversation about the windows, access, and
            priorities. From reachable first-floor glass to taller interior and exterior
            windows, we bring the right tools and an experienced approach. The result is a
            brighter space and a finish that looks clean from every angle.</p>
            <p>Residential customers call us before gatherings, seasonal cleanups, listing a
            home, or whenever the view needs a reset. Commercial customers rely on clean glass
            to make a stronger first impression. Whatever the reason, we make the process
            straightforward and the outcome seriously satisfying.</p>
            """,
        ),
        (
            "Pressure Washing",
            "pressure-washing",
            "A careful exterior wash for siding, driveways, walkways, and outdoor surfaces.",
            """
            <p>Outdoor surfaces collect dirt, algae, weather stains, and grime over time.
            Vossome pressure washing gives those surfaces a fresh start and helps the whole
            property look better maintained.</p>
            <p>We match the cleaning approach to the material instead of treating every surface
            the same. That means thoughtful pressure, sensible preparation, and attention to
            nearby landscaping, doors, windows, and fixtures. We will review the work area and
            explain what to expect before cleaning begins.</p>
            <p>Pressure washing is a practical way to refresh high-visibility areas around a
            home or business. Pair it with window cleaning for an exterior reset that brings
            back the color, contrast, and curb appeal that buildup has been hiding.</p>
            """,
        ),
        (
            "Gutter Cleaning",
            "gutter-cleaning",
            "Clear, tidy gutters that help rainwater move where it should.",
            """
            <p>Clogged gutters can overflow, stain exterior surfaces, and send water toward
            places it does not belong. Vossome removes leaves and accumulated debris so your
            gutter system can get back to doing its job.</p>
            <p>We approach the work carefully, keep the surrounding area as tidy as possible,
            and let you know if we notice an obvious concern while cleaning. Regular service is
            especially useful after heavy leaf fall or when overhanging trees keep refilling
            the system.</p>
            <p>Gutter cleaning fits naturally alongside window and exterior cleaning. One visit
            can address several of the most visible—and most easily postponed—maintenance jobs
            around your property.</p>
            """,
        ),
        (
            "Concrete Patio Cleaning",
            "concrete-patio-cleaning",
            "Bring your patio back from stains and buildup so it feels ready to enjoy again.",
            """
            <p>A concrete patio is where everyday outdoor life happens, which also means it
            collects dirt, organic buildup, weather marks, and traffic stains. Vossome concrete
            patio cleaning cuts through that tired surface layer and restores a cleaner, more
            inviting look.</p>
            <p>We assess the patio and surrounding edges before starting, then use an
            appropriate cleaning process for the condition of the concrete. The goal is an even
            result without careless overspray around doors, siding, furniture, or landscaping.</p>
            <p>Whether you are getting ready to host, opening the outdoor space for the season,
            or simply tired of looking at years of buildup, a professional clean can make the
            patio feel like part of the home again. That is outdoor living made
            #awesomeVossome.</p>
            """,
        ),
    ]

    for order, (title, slug, summary, body) in enumerate(services, start=1):
        Service.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "summary": summary,
                "body": body,
                "meta_title": f"{title} in St. Charles, MO | Vossome",
                "meta_description": f"{summary} Call Vossome at (314) 775-1080 for a quote.",
                "is_published": True,
                "call_to_action_label": "Get your free quote",
                "call_to_action_url": "/contact/",
                "display_order": order,
            },
        )

    faqs = [
        (
            "What areas does Vossome serve?",
            "Vossome serves St. Charles and nearby communities throughout the St. Louis area. "
            "Send us your address with your quote request and we will confirm availability.",
        ),
        (
            "Do you clean both residential and commercial windows?",
            "Yes. We clean windows for homes and businesses, with the scope and access reviewed "
            "before the work is scheduled.",
        ),
        (
            "Can I combine services in one visit?",
            "Absolutely. Window cleaning can often be paired with gutter cleaning, pressure "
            "washing, or concrete patio cleaning. Tell us everything on your list when you ask "
            "for a quote.",
        ),
        (
            "How do I request a quote?",
            "Use the contact form or call (314) 775-1080. Share the property location, services "
            "you need, and any useful details so we can follow up with a clear next step.",
        ),
    ]
    for order, (question, answer) in enumerate(faqs, start=1):
        FAQ.objects.update_or_create(
            question=question,
            defaults={"answer": answer, "is_published": True, "display_order": order},
        )


def remove_vossome_seed(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    Service = apps.get_model("core", "Service")
    FAQ = apps.get_model("core", "FAQ")

    Service.objects.filter(
        slug__in=[
            "window-cleaning",
            "pressure-washing",
            "gutter-cleaning",
            "concrete-patio-cleaning",
        ]
    ).delete()
    FAQ.objects.filter(
        question__in=[
            "What areas does Vossome serve?",
            "Do you clean both residential and commercial windows?",
            "Can I combine services in one visit?",
            "How do I request a quote?",
        ]
    ).delete()
    SiteSettings.objects.filter(pk=1, site_name="Vossome Window Cleaning").delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0003_page_open_graph_description_page_open_graph_image_and_more")]

    operations = [migrations.RunPython(seed_vossome_content, remove_vossome_seed)]