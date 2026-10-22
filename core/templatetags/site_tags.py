from django import template
from django.utils.safestring import mark_safe
from html.parser import HTMLParser


register = template.Library()


@register.filter
def absolute_url(value, request):
    if not value:
        return ""
    return request.build_absolute_uri(value)


class _WindowSectionParser(HTMLParser):
    """Find top-level CMS headings without rewriting the editor's HTML."""

    _void_tags = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.starts = []
        self.depth = 0
        self.line_offsets = [0]
        for line in html.splitlines(keepends=True):
            self.line_offsets.append(self.line_offsets[-1] + len(line))

    def handle_starttag(self, tag, attrs):
        if self.depth == 0 and tag in {"h2", "section"}:
            line, column = self.getpos()
            attributes = dict(attrs)
            kind = attributes.get("data-window-chapter", "") if tag == "h2" else ""
            if tag == "section" and (
                attributes.get("data-window-chapter") == "pricing"
                or "window-pricing" in attributes.get("class", "").split()
            ):
                kind = "pricing"
            self.starts.append((self.line_offsets[line - 1] + column, kind))
        if tag not in self._void_tags:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag not in self._void_tags:
            self.depth = max(0, self.depth - 1)


@register.filter
def window_content_sections(body):
    """Group CMS content for the window layout; never replace its copy or prices."""
    body = body or ""
    parser = _WindowSectionParser(body)
    parser.feed(body)
    if not parser.starts:
        return [{"kind": "other", "html": mark_safe(body)}]

    allowed = {"intro", "pricing", "adventure", "transparent", "way", "ready"}
    sections = []
    for index, (start, kind) in enumerate(parser.starts):
        end = parser.starts[index + 1][0] if index + 1 < len(parser.starts) else len(body)
        # Keep any content before the first heading, including future CMS edits.
        content = (body[:start] if index == 0 else "") + body[start:end]
        sections.append({"kind": kind if kind in allowed else "other", "html": mark_safe(content)})
    ready = next((section for section in sections if section["kind"] == "ready"), sections[-1])
    ready["final_action"] = True
    return sections