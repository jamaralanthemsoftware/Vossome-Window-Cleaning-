from django.http import JsonResponse


class HealthCheckMiddleware:
    """Answer platform health probes before Django validates their internal host."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/" and request.method in {"GET", "HEAD"}:
            return JsonResponse({"status": "ok"})
        return self.get_response(request)