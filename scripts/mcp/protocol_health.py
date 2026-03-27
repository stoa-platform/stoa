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
protocol_health.py — MCP Protocol Health Tests (CAB-1857)

Verifies the MCP protocol stack is healthy end-to-end:
  1. Infrastructure health  (/health, /health/ready, /health/live)
  2. MCP discovery          (/mcp, /mcp/capabilities, /mcp/health)
  3. OAuth discovery        (/.well-known/oauth-protected-resource, /oauth-authorization-server)
  4. Tool listing           (POST /mcp/tools/list, GET /mcp/v1/tools)
  5. Tool call round-trip   (POST /mcp/tools/call — first tool from list, if any)

Prerequisites:
  pip install requests

Usage:
  # Local gateway (no auth):
  STOA_GATEWAY_URL=http://localhost:8080 python3 protocol_health.py

  # Staging with Bearer token:
  STOA_GATEWAY_URL=https://mcp.gostoa.dev STOA_BEARER_TOKEN=<jwt> python3 protocol_health.py

Exit codes:
  0  All tests passed
  1  One or more tests failed
"""

import json
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
TIMEOUT = int(os.environ.get("STOA_TEST_TIMEOUT", "10"))

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

def _headers() -> dict:
    h = {"Accept": "application/json"}
    if BEARER_TOKEN:
        h["Authorization"] = f"Bearer {BEARER_TOKEN}"
    return h


def get(path: str) -> requests.Response:
    return requests.get(f"{GATEWAY_URL}{path}", headers=_headers(), timeout=TIMEOUT)


def post(path: str, body: dict) -> requests.Response:
    h = _headers()
    h["Content-Type"] = "application/json"
    return requests.post(f"{GATEWAY_URL}{path}", headers=h, json=body, timeout=TIMEOUT)


# ── Test groups ───────────────────────────────────────────────────────────────

def test_infrastructure_health() -> None:
    section("1. Infrastructure health")

    for path in ["/health", "/health/ready", "/health/live"]:
        try:
            r = get(path)
            if r.status_code == 200:
                ok(f"GET {path}", f"HTTP 200")
            else:
                fail(f"GET {path}", f"expected 200, got {r.status_code}")
        except requests.RequestException as e:
            fail(f"GET {path}", str(e))


def test_mcp_discovery() -> None:
    section("2. MCP discovery")

    # GET /mcp
    try:
        r = get("/mcp")
        if r.status_code != 200:
            fail("GET /mcp", f"expected 200, got {r.status_code}")
            return
        body = r.json()
        if "protocol_version" not in body:
            fail("GET /mcp — protocol_version field", "field missing from response")
        else:
            ok("GET /mcp — protocol_version", body.get("protocol_version", ""))
        if "endpoints" in body and "tools_list" in body["endpoints"]:
            ok("GET /mcp — endpoints.tools_list", body["endpoints"]["tools_list"])
        else:
            fail("GET /mcp — endpoints.tools_list", "missing endpoints.tools_list")
    except (requests.RequestException, ValueError) as e:
        fail("GET /mcp", str(e))

    # GET /mcp/capabilities
    try:
        r = get("/mcp/capabilities")
        if r.status_code != 200:
            fail("GET /mcp/capabilities", f"expected 200, got {r.status_code}")
        else:
            body = r.json()
            has_cap = "capabilities" in body
            ok("GET /mcp/capabilities", "capabilities field present" if has_cap else "(empty body OK)")
    except (requests.RequestException, ValueError) as e:
        fail("GET /mcp/capabilities", str(e))

    # GET /mcp/health
    try:
        r = get("/mcp/health")
        if r.status_code == 200:
            ok("GET /mcp/health", "HTTP 200")
        else:
            fail("GET /mcp/health", f"expected 200, got {r.status_code}")
    except requests.RequestException as e:
        fail("GET /mcp/health", str(e))


def test_oauth_discovery() -> None:
    section("3. OAuth discovery (mTLS bypass paths)")

    # GET /.well-known/oauth-protected-resource
    try:
        r = get("/.well-known/oauth-protected-resource")
        if r.status_code != 200:
            fail("GET /.well-known/oauth-protected-resource", f"expected 200, got {r.status_code}")
        else:
            body = r.json()
            if "authorization_servers" in body:
                ok(
                    "GET /.well-known/oauth-protected-resource",
                    f"authorization_servers[0]={body['authorization_servers'][0]!r}",
                )
            else:
                fail(
                    "GET /.well-known/oauth-protected-resource — authorization_servers",
                    "field missing",
                )
    except (requests.RequestException, ValueError) as e:
        fail("GET /.well-known/oauth-protected-resource", str(e))

    # GET /.well-known/oauth-authorization-server
    try:
        r = get("/.well-known/oauth-authorization-server")
        if r.status_code != 200:
            fail("GET /.well-known/oauth-authorization-server", f"expected 200, got {r.status_code}")
        else:
            body = r.json()
            has_token_ep = "token_endpoint" in body
            ok(
                "GET /.well-known/oauth-authorization-server",
                f"token_endpoint present={has_token_ep}",
            )
    except (requests.RequestException, ValueError) as e:
        fail("GET /.well-known/oauth-authorization-server", str(e))


def test_tool_listing() -> list:
    """Returns tool list (may be empty) for use by round-trip test."""
    section("4. Tool listing")
    tools: list = []

    # POST /mcp/tools/list
    try:
        r = post("/mcp/tools/list", {})
        if r.status_code != 200:
            fail("POST /mcp/tools/list", f"expected 200, got {r.status_code}")
        else:
            body = r.json()
            if "tools" in body and isinstance(body["tools"], list):
                tools = body["tools"]
                ok("POST /mcp/tools/list", f"{len(tools)} tool(s) registered")
            else:
                fail("POST /mcp/tools/list — tools array", "field missing or not an array")
    except (requests.RequestException, ValueError) as e:
        fail("POST /mcp/tools/list", str(e))

    # GET /mcp/v1/tools (REST variant)
    try:
        r = get("/mcp/v1/tools")
        if r.status_code != 200:
            fail("GET /mcp/v1/tools", f"expected 200, got {r.status_code}")
        else:
            body = r.json()
            if isinstance(body, list):
                ok("GET /mcp/v1/tools", f"{len(body)} tool(s) in REST endpoint")
            else:
                fail("GET /mcp/v1/tools", "expected JSON array response")
    except (requests.RequestException, ValueError) as e:
        fail("GET /mcp/v1/tools", str(e))

    return tools


def test_tool_call_roundtrip(tools: list) -> None:
    section("5. Tool call round-trip")

    if not tools:
        skip("POST /mcp/tools/call", "no tools registered — deploy a tool and re-run")
        return

    tool = tools[0]
    tool_name = tool.get("name", "")
    if not tool_name:
        skip("POST /mcp/tools/call", "first tool has no name field")
        return

    try:
        r = post("/mcp/tools/call", {"name": tool_name, "arguments": {}})
        if r.status_code in (200, 422):
            # 422 = valid invocation but schema validation failed on empty args — still a round-trip
            ok(
                f"POST /mcp/tools/call ({tool_name!r})",
                f"HTTP {r.status_code} — gateway routed the call",
            )
        elif r.status_code == 400:
            # Gateway accepted and forwarded, upstream returned error — round-trip succeeded
            ok(
                f"POST /mcp/tools/call ({tool_name!r})",
                "HTTP 400 — gateway routed; upstream rejected empty args (expected)",
            )
        else:
            fail(
                f"POST /mcp/tools/call ({tool_name!r})",
                f"unexpected status {r.status_code}: {r.text[:120]}",
            )
    except (requests.RequestException, ValueError) as e:
        fail(f"POST /mcp/tools/call ({tool_name!r})", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n{_color(BOLD + 'STOA MCP Protocol Health', BOLD)}")
    print(f"  Gateway : {_color(GATEWAY_URL, BOLD)}")
    print(f"  Auth    : {'Bearer <token>' if BEARER_TOKEN else _color('anonymous', YELLOW)}")
    print(f"  Timeout : {TIMEOUT}s")

    t0 = time.monotonic()

    test_infrastructure_health()
    test_mcp_discovery()
    test_oauth_discovery()
    tools = test_tool_listing()
    test_tool_call_roundtrip(tools)

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
