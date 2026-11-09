"""Security response headers for the Control Plane API.

Swagger UI (``/docs``) and ReDoc (``/redoc``) ship inline bootstrap scripts and
load bundles from jsDelivr, so they need a dedicated Content-Security-Policy.
That policy must not be attached to the rest of the API (CAB-2587).

``/v1/docs`` is the docs-search API, not interactive documentation, and stays
on the application policy. ``/openapi.json`` is JSON and stays there too.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# JSON and other application responses. No scripts, styles, or framing.
# Locked by tests/test_regression_cab_2587_docs_csp.py — do not relax this
# so Swagger or ReDoc can render.
APPLICATION_CSP = (
    "default-src 'none'; "
    "script-src 'none'; "
    "style-src 'none'; "
    "img-src 'none'; "
    "font-src 'none'; "
    "connect-src 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# Minimum policy for the FastAPI Swagger UI and ReDoc HTML pages:
# - script-src: inline bootstrap plus swagger-ui-bundle / redoc.standalone.js
#   on jsDelivr. Swagger UI still evaluates a small amount of code.
# - style-src: Swagger UI's stylesheet is served from the same CDN, and both
#   UIs inject inline styles.
# - img-src: FastAPI favicon and data-URI icons.
# - font-src: data-URI fonts embedded by Swagger UI CSS.
# - connect-src: the page fetches /openapi.json on the same origin.
#   The public Swagger validator is intentionally not allowed.
INTERACTIVE_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)

_SECURITY_HEADER_VALUES: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("x-xss-protection", "0"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("permissions-policy", "camera=(), microphone=(), geolocation=()"),
)


def is_interactive_docs_path(path: str) -> bool:
    """Return True for Swagger UI and ReDoc routes only.

    Match the exact path or a slash-separated child (``/docs/oauth2-redirect``).
    ``/docs-evil`` and ``/v1/docs`` do not match.
    """
    return path == "/docs" or path.startswith("/docs/") or path == "/redoc" or path.startswith("/redoc/")


def content_security_policy_for_path(path: str) -> str:
    """Return the CSP that applies to ``path``."""
    if is_interactive_docs_path(path):
        return INTERACTIVE_DOCS_CSP
    return APPLICATION_CSP


class SecurityHeadersMiddleware:
    """Pure ASGI middleware that sets security headers on every HTTP response.

    The Content-Security-Policy value depends on the request path. Other
    security headers are the same for application and documentation routes.
    An existing header of the same name is replaced so a looser policy cannot
    be appended beside the strict one.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        csp = content_security_policy_for_path(path)

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["content-security-policy"] = csp
                for name, value in _SECURITY_HEADER_VALUES:
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
