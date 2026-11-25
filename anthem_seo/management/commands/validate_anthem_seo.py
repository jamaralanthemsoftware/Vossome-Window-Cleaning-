from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from anthem_seo.blogs import sync_anthem_blogs
from anthem_seo.contract import BundleError, load_bundle
from anthem_seo.records import record_for_reverse_id
from anthem_seo.routing import validate_database_routes


class Command(BaseCommand):
    help = "Validate the versioned GitHub-managed SEO and blog bundle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Also sync blog posts and verify every manifest binding against the current database.",
        )

    def handle(self, *args, **options):
        try:
            bundle = load_bundle()
        except BundleError as exc:
            raise CommandError(str(exc)) from exc
        if options["strict"]:
            try:
                sync_anthem_blogs(bundle=bundle)
                posts = bundle.get("posts") or {}
                for binding in bundle["manifest"]["bindings"]:
                    reverse_id = binding["cms_ref"]["reverse_id"]
                    record = record_for_reverse_id(reverse_id)
                    if record is None:
                        raise CommandError(
                            f"Binding {binding['item_id']} ({reverse_id}) does not match any page, service, or blog post."
                        )
                    post_doc = posts.get((binding["item_id"], binding["language"]))
                    is_draft_post = bool(
                        post_doc and post_doc.get("post", {}).get("status") == "draft"
                    )
                    if not is_draft_post and not record.is_public:
                        raise CommandError(
                            f"Binding {binding['item_id']} is not published for {binding['language']}."
                        )
                validate_database_routes()
            except BundleError as exc:
                raise CommandError(str(exc)) from exc
            except DatabaseError as exc:
                raise CommandError(f"Strict SEO database validation failed: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Valid Anthem SEO bundle: {bundle['digest']} "
                f"({len(bundle['pages'])} active page documents, "
                f"{len(bundle.get('posts', {}))} blog post documents)"
            )
        )
