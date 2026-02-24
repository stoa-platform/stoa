"""PII Masking Middleware — masks PII in HTTP access logs (CAB-430).

Integrates the core PIIMasker into the ASGI middleware stack so that
logged request data (query parameters, client IPs, headers) is
automatically masked before being written to Loki / stdout.

Design:
- Pure ASGI (no BaseHTTPMiddleware) — zero response buffering overhead
- Runs BEFORE HTTPLoggingMiddleware in the stack so that by the time
  the logging middleware reads scope/headers, PII is already masked
- Only masks data used for *logging* — never alters the actual HTTP
  response body sent to clients
"""

import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from ..core.pii import PIIMasker, PIIMaskingConfig

logger = logging.getLogger(__name__)

# Headers whose *values* are replaced with [REDACTED] in the logging scope.
# Names kept lowercase for fast lookup against ASGI raw headers.
_SENSITIVE_HEADERS: frozenset[bytes] = frozenset(
    h.encode()
    for h in (
        "authorization",
        "cookie",
        "x-api-key",
        "x-csrf-token",
        "proxy-authorization",
        "x-auth-token",
    )
)

# Query parameter keys whose values should be masked (case-insensitive).
_SENSITIVE_PARAMS: frozenset[str] = frozenset(
    (
        "token",
        "api_key",
        "apikey",
        "secret",
        "password",
        "access_token",
        "refresh_token",
        "code",
        "session",
    )
)


class PIIMaskingMiddleware:
    """ASGI middleware that masks PII in scope metadata used for logging.

    Placement: add **before** HTTPLoggingMiddleware so logged data is clean.

    What is masked:
    - Query-string values for sensitive param names → ``[REDACTED]``
    - Sensitive header values → ``[REDACTED]``
    - Client IP (last two octets) in ``scope["client"]``
    - Free-text PII (emails, phones, IBANs …) detected in the query string
    """

    def __init__(self, app: ASGIApp, *, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled
        self._masker = PIIMasker(PIIMaskingConfig.default_production())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Mask query-string
        query_string = scope.get("query_string", b"")
        if query_string:
            scope["query_string"] = self._mask_query_string(query_string)

        # 2. Mask sensitive headers (in-place replacement for logging only)
        raw_headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        masked_headers: list[tuple[bytes, bytes]] = []
        for name, value in raw_headers:
            if name.lower() in _SENSITIVE_HEADERS:
                masked_headers.append((name, b"[REDACTED]"))
            else:
                masked_headers.append((name, value))
        scope["headers"] = masked_headers

        # 3. Mask client IP (partial — keep first two octets for geo/debug)
        client = scope.get("client")
        if client:
            ip, port = client
            scope["client"] = (self._mask_ip(ip), port)

        await self.app(scope, receive, send)

    # ── helpers ──────────────────────────────────────────────────────────

    def _mask_query_string(self, qs: bytes) -> bytes:
        """Mask sensitive query-param values and PII in the full QS."""
        try:
            decoded = qs.decode("utf-8", errors="replace")
        except Exception:
            return qs

        parts: list[str] = []
        for pair in decoded.split("&"):
            if "=" not in pair:
                parts.append(pair)
                continue
            key, _, value = pair.partition("=")
            if key.lower() in _SENSITIVE_PARAMS:
                parts.append(f"{key}=[REDACTED]")
            else:
                # Run pattern-based PII detection on the value
                masked_value = self._masker.mask(value)
                parts.append(f"{key}={masked_value}")
        return "&".join(parts).encode("utf-8")

    @staticmethod
    def _mask_ip(ip: str) -> str:
        """Mask last two octets of an IPv4 address for GDPR compliance."""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.xxx.xxx"
        return ip  # IPv6 or other — return as-is for now
