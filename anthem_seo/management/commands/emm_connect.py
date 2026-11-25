"""Pair with Anthem CRM via an EVC1 connection code and run an initial signed poll."""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from anthem_seo.contract import BundleError, bundle_root, load_bundle
from anthem_seo.emm import decode_pairing_code, poll_once, register_connector, resolve_emm_config


class Command(BaseCommand):
    help = "Pair and verify the Anthem CRM Django CMS connector (EVC1 connection code)."

    def add_arguments(self, parser):
        parser.add_argument(
            "pairing_code",
            nargs="?",
            type=str,
            default="",
            help="Anthem CRM connection code starting with EVC1.",
        )
        parser.add_argument(
            "--no-poll",
            action="store_true",
            help="Only decode/validate config without sending a live poll to Anthem CRM.",
        )

    def handle(self, *args, **options):
        raw_code = (options["pairing_code"] or "").strip() or (
            getattr(settings, "EMM_PAIRING_CODE", "") or ""
        ).strip()

        if raw_code:
            try:
                decoded = decode_pairing_code(raw_code)
            except Exception as exc:
                raise CommandError(f"Could not decode pairing code: {exc}") from exc
            site_id = decoded["site_id"]
            endpoint = decoded["endpoint"] or resolve_emm_config()["endpoint"]
            secret = decoded["token"] or resolve_emm_config()["secret"]
            site_url = decoded["home_url"] or resolve_emm_config()["home_url"]
        else:
            cfg = resolve_emm_config()
            site_id = cfg["site_id"]
            endpoint = cfg["endpoint"]
            secret = cfg["secret"]
            site_url = cfg["home_url"]

        if not site_id or not secret:
            raise CommandError(
                "Missing site_id or token. Pass an EVC1 code or set EMM_PAIRING_CODE."
            )

        manifest_path = bundle_root() / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("site_id") != site_id:
                    manifest["site_id"] = site_id
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except Exception as exc:
                raise CommandError(f"Failed updating manifest.json: {exc}") from exc

        try:
            load_bundle()
        except BundleError as exc:
            raise CommandError(f"Anthem SEO bundle validation failed: {exc}") from exc

        if options["no_poll"]:
            self.stdout.write(
                self.style.SUCCESS(f"EMM config validated for site_id={site_id}.")
            )
            return

        try:
            if raw_code:
                reg = register_connector(
                    site_id=site_id,
                    poll_endpoint=endpoint,
                    pairing_token=secret,
                    home_url=site_url,
                )
                secret = str(reg.get("client_secret") or secret)
            res = poll_once(
                site_id=site_id,
                endpoint=endpoint,
                secret=secret,
                site_url=site_url,
            )
            if int(res.get("commands_processed") or 0) > 0:
                poll_once(
                    site_id=site_id,
                    endpoint=endpoint,
                    secret=secret,
                    site_url=site_url,
                )
        except Exception as exc:
            raise CommandError(f"Live connector poll failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Connected and polled Anthem CRM (site_id={site_id}, "
                f"commands_processed={res.get('commands_processed', 0)})."
            )
        )
