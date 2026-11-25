from .routing import begin_request_routes, end_request_routes, enforce_route


class AnthemSeoRoutingMiddleware:
    """Reject stale CMS paths and honor explicit historical redirects."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = begin_request_routes()
        try:
            response = enforce_route(request)
            if response is not None:
                return response
            return self.get_response(request)
        finally:
            end_request_routes(token)
