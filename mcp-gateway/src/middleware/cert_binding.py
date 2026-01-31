"""RFC 8705 Certificate Binding Validation Middleware (CAB-868).

Validates that the certificate fingerprint in the JWT ``cnf`` claim matches
the certificate presented by the client (via F5/nginx header).

Architecture::

    Client → F5/Nginx → MCP Gateway → Backend APIs
                  │            │
                  │            └─ Validates: JWT.cnf.x5t#S256 == Header fingerprint
                  │
                  └─ Header: X-SSL-Client-Cert-SHA256 (SHA-256 fingerprint)

Security requirements (Council):
- Timing-safe comparison via ``secrets.compare_digest``
- Case-insensitive base64url comparison
- Strict mode: if ``cnf`` present but header absent → REJECT
- Feature flag for progressive rollout
"""

import base64
import json
import re
import secrets
from typing import Callable, Optional

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import get_settings

logger = structlog.get_logger(__name__)

_HEX_RE = re.compile(r"^[a-fA-F0-9]+$")


def _normalize_fingerprint(fp: str, fmt: str = "hex") -> Optional[str]:
    """Normalize a fingerprint to lowercase hex for comparison.

    Supports formats: hex, hex_colons, base64url.
    Returns None on invalid input.
    """
    if not fp or not fp.strip():
        return None
    fp = fp.strip()
    try:
        if fmt == "hex_colons" or ":" in fp:
            return fp.replace(":", "").lower()
        if fmt == "hex" or _HEX_RE.match(fp):
            return fp.lower()
        # base64url
        standard = fp.replace("-", "+").replace("_", "/")
        pad = 4 - len(standard) % 4
        if pad != 4:
            standard += "=" * pad
        return base64.b64decode(standard).hex()
    except Exception:
        return None


# Paths exempt from certificate binding validation
_EXEMPT_PREFIXES = (
    "/health",
    "/ready",
    "/live",
    "/metrics",
    "/healthz",
    "/status",
    "/.well-known",
    "/favicon",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _decode_jwt_payload(token: str) -> dict | None:
    """Decode JWT payload without signature verification.

    Only used to extract the ``cnf`` claim. Full signature validation
    is performed by OIDCAuthenticator in auth middleware.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Add padding for base64url
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return None


class CertBindingMiddleware(BaseHTTPMiddleware):
    """Middleware to validate RFC 8705 certificate-bound access tokens.

    Compares JWT ``cnf.x5t#S256`` claim against the certificate fingerprint
    header set by the TLS-terminating proxy (F5/nginx).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        from .metrics import (
            CERT_BINDING_VALIDATIONS_TOTAL,
            CERT_BINDING_FAILURES_TOTAL,
        )

        settings = get_settings()

        # Skip if disabled
        if not settings.cert_binding_enabled:
            return await call_next(request)

        # Skip exempt paths
        if request.url.path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        # Extract Bearer token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # No Bearer token — let auth middleware handle it
            return await call_next(request)

        token = auth_header[7:]  # Strip "Bearer "
        payload = _decode_jwt_payload(token)
        if payload is None:
            return await call_next(request)

        # Extract cnf claim
        cnf = payload.get("cnf")
        if not cnf:
            # No cnf claim = not a cert-bound token (client_secret flow), allow
            return await call_next(request)

        jwt_fingerprint = cnf.get("x5t#S256")
        if not jwt_fingerprint:
            CERT_BINDING_FAILURES_TOTAL.labels(reason="invalid_cnf").inc()
            logger.warning(
                "Certificate binding: cnf claim missing x5t#S256",
                subject=payload.get("sub"),
            )
            return self._reject("Invalid cnf claim: missing x5t#S256")

        # Extract header fingerprint
        header_fingerprint = request.headers.get(settings.cert_binding_header)
        if not header_fingerprint:
            # STRICT: cnf present but header absent → REJECT
            CERT_BINDING_FAILURES_TOTAL.labels(reason="missing_header").inc()
            logger.warning(
                "Certificate binding: header missing for cert-bound token",
                header=settings.cert_binding_header,
                subject=payload.get("sub"),
            )
            return self._reject(
                f"Certificate binding required but {settings.cert_binding_header} header missing"
            )

        # Normalize both fingerprints to hex lowercase (CAB-1024)
        norm_jwt = _normalize_fingerprint(jwt_fingerprint, "base64url")
        norm_header = _normalize_fingerprint(
            header_fingerprint, settings.cert_binding_format
        )

        if not norm_jwt or not norm_header or not secrets.compare_digest(
            norm_jwt, norm_header
        ):
            CERT_BINDING_FAILURES_TOTAL.labels(reason="mismatch").inc()
            logger.warning(
                "Certificate binding: fingerprint mismatch",
                expected_prefix=jwt_fingerprint[:16] + "...",
                received_prefix=header_fingerprint[:16] + "...",
                subject=payload.get("sub"),
            )
            return self._reject("Certificate binding validation failed")

        # Success
        CERT_BINDING_VALIDATIONS_TOTAL.labels(status="success").inc()
        return await call_next(request)

    @staticmethod
    def _reject(message: str) -> JSONResponse:
        """Return 401 Unauthorized with RFC 8705 error."""
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_token",
                "error_description": message,
            },
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )
