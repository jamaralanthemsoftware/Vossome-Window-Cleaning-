"""Database-aware effective URL routing for bound pages in djangocms-master-template."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from django.http import HttpResponseNotFound, HttpResponsePermanentRedirect

from .contract import BundleError, RESERVED_PATHS, load_bundle
from .records import all_cms_records


@dataclass(frozen=True)
class ManagedRoute:
    page: object
    language: str
    cms_path: str
    effective_path: str
    bound: bool = False
    changed: bool = False


_request_routes = ContextVar("anthem_seo_routes", default=None)


def begin_request_routes():
    return _request_routes.set({})


def end_request_routes(token):
    _request_routes.reset(token)


def _path(path):
    if not path or path == "/":
        return "/"
    return "/" + path.strip("/") + "/"


def _document_map(bundle, language):
    return {
        binding["cms_ref"]["reverse_id"]: bundle["pages"].get(
            (binding["item_id"], language)
        )
        for binding in bundle["manifest"]["bindings"]
        if binding["language"] == language
    }


def _bundle_has_route_mutations(bundle) -> bool:
    if bundle.get("redirects"):
        return True
    for doc in (bundle.get("pages") or {}).values():
        if (doc.get("seo") or {}).get("slug"):
            return True
    return False


def all_routes(language="en-us", *, bundle=None):
    bundle = bundle or load_bundle()
    cache = _request_routes.get()
    cache_key = (language, bundle.get("digest", id(bundle)))
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    cms_records = all_cms_records()
    documents = _document_map(bundle, language)
    records = [
        (rec, _path(rec.cms_path), documents.get(rec.reverse_id))
        for rec in cms_records
    ]
    records.sort(key=lambda item: (len(item[1].strip("/").split("/")), item[1]))
    effective_by_cms = {}
    result = []
    for page, cms_path, document in records:
        if page.is_home and document and document.get("seo", {}).get("slug"):
            raise BundleError("homepage slug overrides are not supported")
        if cms_path == "/":
            effective = "/"
        else:
            cms_segments = cms_path.strip("/").split("/")
            effective_segments = []
            for index, segment in enumerate(cms_segments):
                prefix = _path("/".join(cms_segments[: index + 1]))
                ancestor = next(
                    (
                        item
                        for item in records
                        if item[1] == prefix and prefix in effective_by_cms
                    ),
                    None,
                )
                if ancestor:
                    parent_effective = effective_by_cms[prefix].strip("/")
                    effective_segments = (
                        parent_effective.split("/") if parent_effective else []
                    )
                else:
                    effective_segments = effective_segments[:index]
                    effective_segments.append(segment)
                if prefix == cms_path and document:
                    slug = document.get("seo", {}).get("slug", "")
                    if slug:
                        if page.is_home:
                            raise BundleError(
                                "homepage slug overrides are not supported"
                            )
                        effective_segments[-1] = slug
            effective = _path("/".join(effective_segments))
        effective_by_cms[cms_path] = effective
        result.append(
            ManagedRoute(
                page,
                language,
                cms_path,
                effective,
                bound=page.reverse_id in documents,
                changed=effective != cms_path,
            )
        )
    if cache is not None:
        cache[cache_key] = result
    return result


def route_for_page(page, language="en-us", bundle=None):
    if page is None:
        return None
    bundle = bundle or load_bundle()
    if not _bundle_has_route_mutations(bundle) and getattr(page, "cms_path", None):
        cms_path = _path(page.cms_path)
        return ManagedRoute(
            page=page,
            language=language,
            cms_path=cms_path,
            effective_path=cms_path,
            bound=any(
                b["cms_ref"]["reverse_id"] == getattr(page, "reverse_id", None)
                and b["language"] == language
                for b in bundle["manifest"]["bindings"]
            ),
            changed=False,
        )
    return next(
        (
            route
            for route in all_routes(language, bundle=bundle)
            if route.page.reverse_id == getattr(page, "reverse_id", None)
        ),
        None,
    )


def route_for_path(path, language="en-us"):
    bundle = load_bundle()
    if not _bundle_has_route_mutations(bundle):
        return None
    normalized = _path(path)
    return next(
        (
            route
            for route in all_routes(language, bundle=bundle)
            if route.effective_path == normalized and route.bound and route.changed
        ),
        None,
    )


def effective_path(page, language="en-us", bundle=None):
    route = route_for_page(page, language, bundle=bundle)
    return route.effective_path if route else None


def redirect_for_path(path, language="en-us", bundle=None):
    bundle = bundle or load_bundle()
    if not bundle.get("redirects"):
        return None
    normalized = _path(path)
    routes = all_routes(language, bundle=bundle)
    route_targets = {route.effective_path for route in routes}
    for item in bundle["redirects"]:
        if item["language"] == language and _path(item["from"]) == normalized:
            target = _path(item["to"])
            if target not in route_targets:
                raise BundleError("redirect target is not a current effective route")
            return target
    return None


def enforce_route(request, language="en-us"):
    if request.path.startswith(
        (
            "/admin/",
            "/api/",
            "/emm/",
            "/inquiries/",
            "/static/",
            "/media/",
            "/accounts/",
            "/integrations/",
            "/downloads/",
            "/healthz/",
        )
    ):
        return None
    try:
        bundle = load_bundle()
    except BundleError:
        return None
    if not _bundle_has_route_mutations(bundle):
        return None
    routes = all_routes(language, bundle=bundle)
    if any(route.effective_path == _path(request.path) for route in routes):
        return None
    stale = next(
        (
            route
            for route in routes
            if route.cms_path == _path(request.path)
            and route.cms_path != route.effective_path
        ),
        None,
    )
    target = redirect_for_path(request.path, language, bundle=bundle)
    if stale or target:
        if target:
            status = 308 if request.method not in {"GET", "HEAD"} else 301
            response = HttpResponsePermanentRedirect(target)
            response.status_code = status
            return response
        return HttpResponseNotFound("This page has moved.")
    return None


def validate_database_routes():
    bundle = load_bundle()
    all_effective = {}
    for language in bundle["manifest"]["supported_languages"]:
        language_routes = all_routes(language, bundle=bundle)
        for route in language_routes:
            key = (language, route.effective_path)
            if key in all_effective:
                raise BundleError(
                    f"effective route collision: {route.effective_path}"
                )
            all_effective[key] = route
            if route.page.is_home and route.effective_path != "/":
                raise BundleError("homepage cannot have an override path")
            root = (
                route.effective_path.strip("/").split("/", 1)[0]
                if route.effective_path != "/"
                else ""
            )
            if root in RESERVED_PATHS:
                raise BundleError(f"effective route uses reserved root: {root}")
        for route in language_routes:
            cms_key = (language, route.cms_path)
            effective_owner = all_effective.get(cms_key)
            if (
                effective_owner is not None
                and effective_owner.page.reverse_id != route.page.reverse_id
            ):
                raise BundleError(
                    f"stale CMS route collides with effective route: {route.cms_path}"
                )
        for item in bundle["redirects"]:
            if item["language"] != language:
                continue
            source = _path(item["from"])
            if (language, source) in all_effective and source != _path(item["to"]):
                raise BundleError(
                    f"redirect source is a current effective route: {source}"
                )
            target = _path(item["to"])
            if (language, target) not in all_effective:
                raise BundleError(f"redirect target is not current: {target}")
    return all_effective
