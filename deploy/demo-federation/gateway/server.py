#!/usr/bin/env python3
"""
STOA Federation Demo - Mock Gateway
Validates JWT issuer/audience isolation per tenant endpoint.
Zero dependencies (stdlib only).
"""

import json
import base64
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("GATEWAY_PORT", "9000"))
KEYCLOAK_BASE = os.environ.get("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080")
KEYCLOAK_EXTERNAL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
# Optional: accept tokens issued with KC_HOSTNAME_URL (e.g., http://localhost/auth)
KEYCLOAK_HOSTNAME = os.environ.get("KEYCLOAK_HOSTNAME_URL", "")

# Map tenant path prefix to accepted issuers (internal + external + hostname)
TENANT_ACCEPTED_ISSUERS = {}
for _tenant_key in ("alpha", "beta", "gamma"):
    _realm = f"demo-org-{_tenant_key}"
    _issuers = {
        f"{KEYCLOAK_BASE}/realms/{_realm}",
        f"{KEYCLOAK_EXTERNAL}/realms/{_realm}",
    }
    if KEYCLOAK_HOSTNAME:
        _issuers.add(f"{KEYCLOAK_HOSTNAME}/realms/{_realm}")
    TENANT_ACCEPTED_ISSUERS[_tenant_key] = _issuers


def decode_jwt_payload(token: str) -> dict:
    """Base64-decode JWT payload (no signature verification — demo only)."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    # Add padding
    payload += "=" * (4 - len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


class GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[gateway] {args[0]}")

    def _send_json(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body, indent=2).encode())

    def do_GET(self):
        # Health check
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "stoa-federation-gateway"})
            return

        # Route: /api/{tenant}/whoami
        parts = self.path.strip("/").split("/")
        if len(parts) < 2 or parts[0] != "api":
            self._send_json(404, {"error": "Not found", "hint": "Use /api/{alpha|beta|gamma}/whoami"})
            return

        tenant = parts[1]
        if tenant not in TENANT_ACCEPTED_ISSUERS:
            self._send_json(404, {"error": f"Unknown tenant: {tenant}", "valid": list(TENANT_ACCEPTED_ISSUERS.keys())})
            return

        # Extract Bearer token
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"error": "Missing Bearer token"})
            return

        token = auth[7:]
        claims = decode_jwt_payload(token)
        if not claims:
            self._send_json(401, {"error": "Invalid JWT"})
            return

        # Validate issuer
        accepted = TENANT_ACCEPTED_ISSUERS[tenant]
        actual_issuer = claims.get("iss", "")

        if actual_issuer not in accepted:
            self._send_json(403, {
                "error": "Issuer mismatch — cross-realm access denied",
                "tenant": tenant,
                "expected_issuers": sorted(accepted),
                "actual_issuer": actual_issuer,
                "stoa_realm": claims.get("stoa_realm", "unknown"),
            })
            return

        # Success
        self._send_json(200, {
            "status": "authorized",
            "tenant": tenant,
            "issuer": actual_issuer,
            "stoa_realm": claims.get("stoa_realm", "unknown"),
            "subject": claims.get("sub", "unknown"),
            "preferred_username": claims.get("preferred_username", "unknown"),
            "audience": claims.get("aud", []),
            "expires_at": claims.get("exp", 0),
        })


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), GatewayHandler)
    print(f"[gateway] Federation mock gateway listening on :{PORT}")
    print(f"[gateway] Tenants: {list(TENANT_ACCEPTED_ISSUERS.keys())}")
    if KEYCLOAK_HOSTNAME:
        print(f"[gateway] KC_HOSTNAME_URL accepted: {KEYCLOAK_HOSTNAME}")
    server.serve_forever()
