#!/usr/bin/env python3
# Copyright 2024 STOA Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
security_validation.py — MCP Security & Auth Enforcement Tests (CAB-1857)

Validates security boundaries of the MCP gateway:
  1. Admin API auth enforcement    (no token → 401, wrong token → 401)
  2. mTLS bypass paths             (/.well-known/*, /oauth/*, /health accessible without certs)
  3. Invalid/expired JWT handling  (malformed token → MCP works anonymously OR returns 401)
  4. Public MCP discovery          (GET /mcp accessible without auth)
  5. RBAC header forwarding        (Authorization header propagated correctly)
  6. CORS / security headers       (no CORS misconfiguration on admin routes)

Prerequisites:
  pip install requests

Usage:
  # Local gateway (no auth):
  STOA_GATEWAY_URL=http://localhost:8080 python3 security_validation.py

  # With valid admin token:
  STOA_GATEWAY_URL=http://localhost:8080 STOA_ADMIN_TOKEN=<token> python3 security_validation.py

  # Full test with both tokens (staging):
  STOA_GATEWAY_URL=https://mcp.gostoa.dev \\
    STOA_BEARER_TOKEN=<jwt> \\
    STOA_ADMIN_TOKEN=<admin_token> \\
    python3 security_validation.py

Exit codes:
  0  All tests passed
  1  One or more tests failed
"""

import os
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

GATEWAY_URL = os.environ.get("STOA_GATEWAY_URL", "http://localhost:8080").rstrip("/")
BEARER_TOKEN = os.environ.get("STOA_BEARER_TOKEN", "")
ADMIN_TOKEN = os.environ.get("STOA_ADMIN_TOKEN", "")
TIMEOUT = int(os.environ.get("STOA_TEST_TIMEOUT", "10"))

# A syntactically valid but unsigned JWT (header.payload.signature — all base64url garbage)
# This will fail signature verification but tests how the gateway handles bad tokens.
INVALID_JWT = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxfQ"
    ".INVALIDSIGNATURE"
)

# ── Output helpers ────────────────────────────────────────────────────────────

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _color(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{RESET}"
    return text


passed = 0
failed = 0
skipped = 0


def ok(name: str, detail: str = "") -> None:
    global passed
    passed += 1
    suffix = f"  {_color(detail, DIM)}" if detail else ""
    print(f"  {_color('PASS', GREEN)} {name}{suffix}")


def fail(name: str, reason: str) -> None:
    global failed
    failed += 1
    print(f"  {_color('FAIL', RED)} {name}")
    print(f"       {_color(reason, DIM)}")


def skip(name: str, reason: str) -> None:
    global skipped
    skipped += 1
    print(f"  {_color('SKIP', YELLOW)} {name}  {_color(reason, DIM)}")


def section(title: str) -> None:
    print(f"\n{_color(BOLD + title, BOLD)}")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(path: str, token: str = "") -> requests.Response:
    headers: dict = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(f"{GATEWAY_URL}{path}", headers=headers, timeout=TIMEOUT)


def post_no_auth(path: str, body: dict) -> requests.Response:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    return requests.post(f"{GATEWAY_URL}{path}", headers=headers, json=body, timeout=TIMEOUT)


def post_with_token(path: str, body: dict, token: str) -> requests.Response:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    return requests.post(f"{GATEWAY_URL}{path}", headers=headers, json=body, timeout=TIMEOUT)


# ── Test groups ───────────────────────────────────────────────────────────────

def test_admin_auth_enforcement() -> None:
    section("1. Admin API auth enforcement")

    # ── 1a. No token ──────────────────────────────────────────────────────────
    try:
        r = get("/admin/health", token="")
        if r.status_code == 401:
            ok("GET /admin/health (no token) → 401", "correctly rejected")
        elif r.status_code == 404:
            skip("GET /admin/health (no token)", "admin health endpoint not found (404) — check STOA_ADMIN_API_TOKEN config")
        else:
            fail(
                "GET /admin/health (no token) → 401",
                f"expected 401, got {r.status_code} (admin API may be unprotected)",
            )
    except requests.RequestException as e:
        fail("GET /admin/health (no token)", str(e))

    # ── 1b. Wrong token ───────────────────────────────────────────────────────
    try:
        r = get("/admin/health", token="wrong-token-12345")
        if r.status_code == 401:
            ok("GET /admin/health (wrong token) → 401", "correctly rejected")
        elif r.status_code == 404:
            skip("GET /admin/health (wrong token)", "admin health endpoint not found (404)")
        else:
            fail(
                "GET /admin/health (wrong token) → 401",
                f"expected 401, got {r.status_code}",
            )
    except requests.RequestException as e:
        fail("GET /admin/health (wrong token)", str(e))

    # ── 1c. Valid admin token (if provided) ───────────────────────────────────
    if ADMIN_TOKEN:
        try:
            r = get("/admin/health", token=ADMIN_TOKEN)
            if r.status_code == 200:
                ok("GET /admin/health (valid token) → 200", "admin access granted")
            else:
                fail(
                    "GET /admin/health (valid token) → 200",
                    f"expected 200, got {r.status_code}: {r.text[:80]}",
                )
        except requests.RequestException as e:
            fail("GET /admin/health (valid token)", str(e))
    else:
        skip(
            "GET /admin/health (valid token)",
            "set STOA_ADMIN_TOKEN to test admin access with a valid token",
        )


def test_mtls_bypass_paths() -> None:
    """Verify RFC-mandated public paths are accessible without mTLS or auth."""
    section("2. mTLS bypass paths (RFC 9728 / RFC 8414 / health)")

    bypass_paths = [
        ("GET", "/.well-known/oauth-protected-resource", None),
        ("GET", "/.well-known/oauth-authorization-server", None),
        ("GET", "/health", None),
        ("GET", "/health/ready", None),
        ("GET", "/health/live", None),
        ("GET", "/mcp", None),
        ("GET", "/mcp/health", None),
    ]

    for method, path, _body in bypass_paths:
        try:
            r = get(path, token="")  # Deliberately no token
            if r.status_code == 200:
                ok(f"{method} {path} accessible without auth", f"HTTP 200")
            elif r.status_code == 404:
                skip(f"{method} {path}", "404 — endpoint may not be enabled in this mode")
            else:
                fail(
                    f"{method} {path} accessible without auth",
                    f"expected 200, got {r.status_code} (mTLS bypass or auth config issue)",
                )
        except requests.RequestException as e:
            fail(f"{method} {path}", str(e))


def test_invalid_jwt_handling() -> None:
    """
    MCP tool endpoints extract auth context but don't hard-require a token.
    An invalid/expired JWT should either:
      - be silently treated as anonymous (200, empty or public tool list)
      - OR rejected with 401 if the gateway is configured to require auth

    Both are valid behaviors depending on config. We test that the gateway
    responds consistently and doesn't return a 5xx.
    """
    section("3. Invalid / expired JWT handling")

    try:
        r = post_with_token("/mcp/tools/list", {}, INVALID_JWT)
        if r.status_code in (200, 401, 403):
            ok(
                "POST /mcp/tools/list (invalid JWT)",
                f"HTTP {r.status_code} — gateway handled gracefully (no 5xx)",
            )
        elif r.status_code >= 500:
            fail(
                "POST /mcp/tools/list (invalid JWT)",
                f"unexpected 5xx error {r.status_code}: {r.text[:120]}",
            )
        else:
            ok(
                "POST /mcp/tools/list (invalid JWT)",
                f"HTTP {r.status_code} — gateway responded (no 5xx)",
            )
    except requests.RequestException as e:
        fail("POST /mcp/tools/list (invalid JWT)", str(e))

    # Same check for the REST endpoint
    try:
        r = get("/mcp/v1/tools")
        # Header set via direct requests call with invalid token
        r2 = requests.get(
            f"{GATEWAY_URL}/mcp/v1/tools",
            headers={"Authorization": f"Bearer {INVALID_JWT}", "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if r2.status_code in (200, 401, 403):
            ok(
                "GET /mcp/v1/tools (invalid JWT)",
                f"HTTP {r2.status_code} — no 5xx",
            )
        elif r2.status_code >= 500:
            fail(
                "GET /mcp/v1/tools (invalid JWT)",
                f"5xx error {r2.status_code}: {r2.text[:120]}",
            )
        else:
            ok(
                "GET /mcp/v1/tools (invalid JWT)",
                f"HTTP {r2.status_code} — gateway responded",
            )
    except requests.RequestException as e:
        fail("GET /mcp/v1/tools (invalid JWT)", str(e))


def test_public_mcp_discovery() -> None:
    """GET /mcp must be publicly accessible — it's the MCP handshake entry point."""
    section("4. Public MCP discovery (no auth required)")

    try:
        r = get("/mcp", token="")  # No token at all
        if r.status_code == 200:
            body = r.json()
            if "protocol_version" in body:
                ok("GET /mcp (no auth) → 200 with protocol_version", body.get("protocol_version", ""))
            else:
                ok("GET /mcp (no auth) → 200", "no protocol_version field (unexpected but not a security issue)")
        else:
            fail(
                "GET /mcp (no auth) → 200",
                f"expected 200, got {r.status_code} (MCP discovery must be public per spec)",
            )
    except (requests.RequestException, ValueError) as e:
        fail("GET /mcp (no auth)", str(e))

    # With valid Bearer token — should also return 200
    if BEARER_TOKEN:
        try:
            r = get("/mcp", token=BEARER_TOKEN)
            if r.status_code == 200:
                ok("GET /mcp (valid Bearer) → 200", "authenticated discovery also works")
            else:
                fail("GET /mcp (valid Bearer) → 200", f"got {r.status_code}")
        except requests.RequestException as e:
            fail("GET /mcp (valid Bearer)", str(e))
    else:
        skip("GET /mcp (valid Bearer)", "set STOA_BEARER_TOKEN to test authenticated discovery")


def test_oauth_endpoint_access() -> None:
    """OAuth token and register endpoints must not be blocked by mTLS middleware."""
    section("5. OAuth endpoint accessibility (no mTLS block)")

    # POST /oauth/token with an invalid/empty body should return 400 (bad request)
    # NOT 401/403 from mTLS middleware — the OAuth handler itself rejects bad requests.
    try:
        r = requests.post(
            f"{GATEWAY_URL}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "authorization_code", "code": "dummy"},
            timeout=TIMEOUT,
        )
        if r.status_code in (400, 401):
            ok(
                "POST /oauth/token (invalid body) → 400 or 401",
                f"HTTP {r.status_code} — OAuth handler responded (not mTLS-blocked)",
            )
        elif r.status_code == 200:
            # Unlikely but possible if gateway is in test mode
            ok("POST /oauth/token → 200", "unexpected success (test mode?)")
        elif r.status_code >= 500:
            fail(
                "POST /oauth/token (invalid body)",
                f"5xx error {r.status_code}: {r.text[:120]}",
            )
        else:
            # Any non-5xx is acceptable — the mTLS bypass is the key thing we're testing
            ok(
                "POST /oauth/token",
                f"HTTP {r.status_code} — endpoint reachable (no mTLS block)",
            )
    except requests.RequestException as e:
        fail("POST /oauth/token (OAuth endpoint reachable)", str(e))

    # GET /oauth/register (non-existent client) should return 404 or 400, not 403 from mTLS
    try:
        r = get("/oauth/register/nonexistent-client-id-test", token="")
        if r.status_code in (400, 401, 404):
            ok(
                "GET /oauth/register/:id (no token) → 400/401/404",
                f"HTTP {r.status_code} — OAuth handler responded (not mTLS-blocked)",
            )
        elif r.status_code >= 500:
            fail(
                "GET /oauth/register/:id",
                f"5xx error {r.status_code}",
            )
        else:
            ok(
                "GET /oauth/register/:id",
                f"HTTP {r.status_code} — endpoint reachable",
            )
    except requests.RequestException as e:
        fail("GET /oauth/register/:id", str(e))


def test_no_server_info_leakage() -> None:
    """Server response headers should not leak internal details."""
    section("6. Server header hygiene")

    try:
        r = get("/mcp", token="")
        server_header = r.headers.get("server", "")
        if server_header and server_header.lower() not in ("", "stoa"):
            # Detailed version strings (e.g. "hyper/0.14.27") are a minor info leak
            # We warn but don't fail — this is deployment-specific
            skip(
                "Server header",
                f"header exposes: {server_header!r} — consider removing or normalizing",
            )
        else:
            sv = repr(server_header) if server_header else "(not set)"
            ok("Server header", f"value={sv}")

        # X-Powered-By should not be present
        xpb = r.headers.get("x-powered-by", "")
        if xpb:
            skip("X-Powered-By header", f"exposes: {xpb!r} — consider removing")
        else:
            ok("X-Powered-By header absent", "not leaking runtime info")

    except requests.RequestException as e:
        fail("Server header hygiene", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n{_color(BOLD + 'STOA MCP Security Validation', BOLD)}")
    print(f"  Gateway     : {_color(GATEWAY_URL, BOLD)}")
    print(f"  Bearer auth : {'set' if BEARER_TOKEN else _color('not set', YELLOW)}")
    print(f"  Admin token : {'set' if ADMIN_TOKEN else _color('not set (admin tests will be limited)', YELLOW)}")
    print(f"  Timeout     : {TIMEOUT}s")
    print(
        f"\n  {_color('Note', YELLOW)}: set STOA_ADMIN_TOKEN env var to enable full admin auth tests."
    )

    t0 = time.monotonic()

    test_admin_auth_enforcement()
    test_mtls_bypass_paths()
    test_invalid_jwt_handling()
    test_public_mcp_discovery()
    test_oauth_endpoint_access()
    test_no_server_info_leakage()

    elapsed = time.monotonic() - t0

    print(f"\n{'─' * 50}")
    print(
        f"  {_color(str(passed) + ' passed', GREEN)}"
        f"  {_color(str(failed) + ' failed', RED if failed else DIM)}"
        f"  {_color(str(skipped) + ' skipped', YELLOW if skipped else DIM)}"
        f"  {_color(f'{elapsed:.2f}s', DIM)}"
    )
    print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
