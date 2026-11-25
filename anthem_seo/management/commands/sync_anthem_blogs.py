from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from anthem_seo.blogs import sync_anthem_blogs
from anthem_seo.contract import BundleError, load_bundle


class Command(BaseCommand):
    help = "Synchronize Git-managed blog post documents (seo/posts/*.json) into core.models.BlogPost."

    def handle(self, *args, **options):
        try:
            bundle = load_bundle()
            result = sync_anthem_blogs(bundle=bundle)
        except (BundleError, DatabaseError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Synchronized {result['synced']} Anthem blog post(s) "
                f"(digest: {bundle['digest']})"
            )
        )
