"""Safe HTML sanitizer for inbound Anthem SEO / EMM blog post markup."""

from __future__ import annotations

import re

try:
    import bleach
except ImportError:  # pragma: no cover
    bleach = None

ALLOWED_HTML_TAGS = {
    "a",
    "abbr",
    "blockquote",
    "br",
    "caption",
    "code",
    "div",
    "em",
    "figcaption",
    "figure",
    "h2",
    "h3",
    "h4",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

ALLOWED_HTML_ATTRS = {
    "a": {"href", "title", "rel"},
    "div": {"class"},
    "figure": {"class"},
    "h2": {"id"},
    "h3": {"id"},
    "h4": {"id"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "span": {"class"},
    "table": {"class"},
    "th": {"scope"},
}


def safe_html(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(
        r"(?is)<(script|style|iframe|object|embed|form)\b[^>]*>.*?</\1\s*>",
        "",
        value,
    )
    if bleach is not None:
        return bleach.clean(
            cleaned,
            tags=ALLOWED_HTML_TAGS,
            attributes=ALLOWED_HTML_ATTRS,
            protocols=["http", "https", "mailto", "tel", "sms"],
            strip=True,
        )
    return re.sub(
        r"(?is)<(/?)([a-z0-9]+)\b[^>]*>",
        lambda match: f"<{match.group(1)}{match.group(2).lower()}>"
        if match.group(2).lower() in (ALLOWED_HTML_TAGS - {"a", "img"})
        else "",
        cleaned,
    )
