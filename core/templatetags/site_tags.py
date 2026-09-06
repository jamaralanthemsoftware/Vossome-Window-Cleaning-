from django import template


register = template.Library()


@register.filter
def absolute_url(value, request):
    if not value:
        return ""
    return request.build_absolute_uri(value)