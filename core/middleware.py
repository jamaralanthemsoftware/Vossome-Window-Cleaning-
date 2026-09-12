from django.conf import settings
from django.http import JsonResponse


class HealthCheckMiddleware:
    """Answer platform health probes before Django validates their internal host."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/" and request.method in {"GET", "HEAD"}:
            return JsonResponse({"status": "ok"})
        return self.get_response(request)


class ContentSecurityPolicyMiddleware:
    """Apply the configured enforce-mode browser content restrictions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if policy and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = policy
        return response