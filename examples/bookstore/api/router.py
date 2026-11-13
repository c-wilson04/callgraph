"""A minimal HTTP-style router with a middleware chain."""

from domain.validation import ValidationError


class Router:
    def __init__(self):
        self.routes = []
        self.middleware = []

    def route(self, method, pattern):
        def register(handler):
            self.routes.append((method, pattern.strip("/").split("/"), handler))
            return handler

        return register

    def use(self, middleware):
        self.middleware.append(middleware)

    def dispatch(self, request):
        for middleware in self.middleware:
            rejected = middleware(request)
            if rejected:
                return rejected
        handler, params = self.match(request["method"], request["path"])
        if handler is None:
            return {"status": 404}
        try:
            return {"status": 200, "body": handler(request, **params)}
        except ValidationError as exc:
            return {"status": 422, "error": str(exc)}

    def match(self, method, path):
        parts = path.strip("/").split("/")
        for route_method, pattern, handler in self.routes:
            if route_method != method or len(pattern) != len(parts):
                continue
            params = match_segments(pattern, parts)
            if params is not None:
                return handler, params
        return None, {}


def match_segments(pattern, parts):
    params = {}
    for expected, actual in zip(pattern, parts):
        if expected.startswith("{"):
            params[expected[1:-1]] = int(actual) if actual.isdigit() else actual
        elif expected != actual:
            return None
    return params


def authenticate(request):
    if not request.get("token"):
        return {"status": 401}
    return None


def rate_limit(request, _seen={}):
    user = request.get("user", 0)
    _seen[user] = _seen.get(user, 0) + 1
    return None
