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
data_flow.py — MCP End-to-End Data Flow Tests (CAB-1857)

Verifies data flows correctly through the gateway stack:
  1. JSON-RPC style tool listing     (POST /mcp/tools/list)
  2. REST style tool listing         (GET /mcp/v1/tools)
  3. REST tool invocation            (POST /mcp/v1/tools/invoke)
  4. Response headers                (Content-Type, trace ID, rate limit headers)
  5. Request/response schema parity  (tool names match between list and invoke)
  6. Concurrent request handling     (3 parallel tool-list calls)

Prerequisites:
  pip install requests

Usage:
  # Local gateway (no auth):
  STOA_GATEWAY_URL=http://localhost:8080 python3 data_flow.py

  # Staging with Bearer token:
  STOA_GATEWAY_URL=https://mcp.gostoa.dev STOA_BEARER_TOKEN=<jwt> python3 data_flow.py

  # Override timeout:
  STOA_TEST_TIMEOUT=30 STOA_GATEWAY_URL=... python3 data_flow.py

Exit codes:
  0  All tests passed
  1  One or more tests failed
"""

import os
import sys
import time
import threading
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

GATEWAY_URL = os.environ.get("STOA_GATEWAY_URL", "http://localhost:8080").rstrip("/")
BEARER_TOKEN = os.environ.get("STOA_BEARER_TOKEN", "")
TIMEOUT = int(os.environ.get("STOA_TEST_TIMEOUT", "10"))
CONCURRENCY = 3  # parallel requests for concurrency test

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

def test_jsonrpc_tool_listing() -> Optional[list]:
    """Returns tool list for use by downstream tests."""
    section("1. JSON-RPC tool listing (POST /mcp/tools/list)")

    try:
        t0 = time.monotonic()
        r = post("/mcp/tools/list", {})
        latency_ms = (time.monotonic() - t0) * 1000

        if r.status_code != 200:
            fail("POST /mcp/tools/list status", f"expected 200, got {r.status_code}: {r.text[:80]}")
            return None

        ok("POST /mcp/tools/list status", f"HTTP 200 in {latency_ms:.0f}ms")

        body = r.json()
        if not isinstance(body, dict):
            fail("POST /mcp/tools/list body", f"expected object, got {type(body).__name__}")
            return None

        if "tools" not in body:
            fail("POST /mcp/tools/list — tools field", "field missing")
            return None

        tools = body["tools"]
        if not isinstance(tools, list):
            fail("POST /mcp/tools/list — tools type", f"expected list, got {type(tools).__name__}")
            return None

        ok("POST /mcp/tools/list — tools array", f"{len(tools)} tool(s)")

        # Validate tool schema for each entry
        schema_errors = []
        for i, tool in enumerate(tools):
            if not isinstance(tool.get("name"), str) or not tool["name"]:
                schema_errors.append(f"tools[{i}].name is missing or empty")
        if schema_errors:
            fail("POST /mcp/tools/list — tool schemas", "; ".join(schema_errors[:3]))
        else:
            ok("POST /mcp/tools/list — tool schemas", "all tools have required name field")

        return tools

    except (requests.RequestException, ValueError) as e:
        fail("POST /mcp/tools/list", str(e))
        return None


def test_rest_tool_listing() -> Optional[list]:
    """Returns REST tool list for schema parity check."""
    section("2. REST tool listing (GET /mcp/v1/tools)")

    try:
        t0 = time.monotonic()
        r = get("/mcp/v1/tools")
        latency_ms = (time.monotonic() - t0) * 1000

        if r.status_code != 200:
            fail("GET /mcp/v1/tools status", f"expected 200, got {r.status_code}: {r.text[:80]}")
            return None

        ok("GET /mcp/v1/tools status", f"HTTP 200 in {latency_ms:.0f}ms")

        body = r.json()
        if not isinstance(body, list):
            fail("GET /mcp/v1/tools body", f"expected array, got {type(body).__name__}")
            return None

        ok("GET /mcp/v1/tools — array response", f"{len(body)} tool(s)")
        return body

    except (requests.RequestException, ValueError) as e:
        fail("GET /mcp/v1/tools", str(e))
        return None


def test_schema_parity(jsonrpc_tools: Optional[list], rest_tools: Optional[list]) -> None:
    section("3. Schema parity (JSON-RPC vs REST tool lists)")

    if jsonrpc_tools is None or rest_tools is None:
        skip("Schema parity", "one or both tool lists failed to load")
        return

    jrpc_names = {t["name"] for t in jsonrpc_tools if "name" in t}
    rest_names = {t["name"] for t in rest_tools if "name" in t}

    if jrpc_names == rest_names:
        ok("JSON-RPC vs REST tool names match", f"{len(jrpc_names)} tool(s)")
    else:
        only_jrpc = jrpc_names - rest_names
        only_rest = rest_names - jrpc_names
        parts = []
        if only_jrpc:
            parts.append(f"only in JSON-RPC: {sorted(only_jrpc)}")
        if only_rest:
            parts.append(f"only in REST: {sorted(only_rest)}")
        fail("JSON-RPC vs REST tool names match", "; ".join(parts))


def test_rest_tool_invocation(rest_tools: Optional[list]) -> None:
    section("4. REST tool invocation (POST /mcp/v1/tools/invoke)")

    if rest_tools is None:
        skip("POST /mcp/v1/tools/invoke", "REST tool list unavailable")
        return

    if not rest_tools:
        skip("POST /mcp/v1/tools/invoke", "no tools registered — deploy a tool and re-run")
        return

    tool_name = rest_tools[0].get("name", "")
    if not tool_name:
        skip("POST /mcp/v1/tools/invoke", "first tool has no name")
        return

    try:
        t0 = time.monotonic()
        r = post("/mcp/v1/tools/invoke", {"tool": tool_name, "arguments": {}})
        latency_ms = (time.monotonic() - t0) * 1000

        # 200/400/422 all indicate the gateway routed the request correctly
        if r.status_code in (200, 400, 422):
            ok(
                f"POST /mcp/v1/tools/invoke ({tool_name!r})",
                f"HTTP {r.status_code} in {latency_ms:.0f}ms — gateway routed the call",
            )
        else:
            fail(
                f"POST /mcp/v1/tools/invoke ({tool_name!r})",
                f"unexpected status {r.status_code}: {r.text[:120]}",
            )
    except (requests.RequestException, ValueError) as e:
        fail(f"POST /mcp/v1/tools/invoke ({tool_name!r})", str(e))


def test_response_headers() -> None:
    section("5. Response headers")

    try:
        r = post("/mcp/tools/list", {})
        if r.status_code != 200:
            skip("Response headers", f"tool-list returned {r.status_code}, skipping header checks")
            return

        # Content-Type must be application/json
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            ok("Content-Type: application/json", ct)
        else:
            fail("Content-Type: application/json", f"got: {ct!r}")

        # Trace ID — gateway adds X-Request-Id or X-Trace-Id
        trace_id = (
            r.headers.get("x-request-id")
            or r.headers.get("x-trace-id")
            or r.headers.get("traceparent")
        )
        if trace_id:
            ok("Trace ID header present", f"{trace_id[:40]}")
        else:
            # Not every deployment has trace headers enabled — warn but don't fail
            skip("Trace ID header", "x-request-id / x-trace-id / traceparent not set (tracing may be disabled)")

        # Rate limit headers (X-RateLimit-*)
        rl_remaining = r.headers.get("x-ratelimit-remaining") or r.headers.get("ratelimit-remaining")
        if rl_remaining:
            ok("Rate limit headers", f"X-RateLimit-Remaining={rl_remaining}")
        else:
            skip("Rate limit headers", "not present (rate limiting may be disabled in this deployment)")

    except (requests.RequestException, ValueError) as e:
        fail("Response headers", str(e))


def test_concurrent_requests() -> None:
    section(f"6. Concurrent request handling ({CONCURRENCY} parallel tool-list calls)")

    results: list = []
    errors: list = []

    def worker() -> None:
        try:
            r = post("/mcp/tools/list", {})
            results.append(r.status_code)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(CONCURRENCY)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=TIMEOUT + 5)
    elapsed_ms = (time.monotonic() - t0) * 1000

    if errors:
        fail("Concurrent requests", f"{len(errors)} error(s): {errors[0]}")
        return

    unexpected = [s for s in results if s != 200]
    if unexpected:
        fail("Concurrent requests — all 200", f"got unexpected statuses: {unexpected}")
    else:
        ok(
            f"Concurrent requests — all {len(results)} returned 200",
            f"{elapsed_ms:.0f}ms total",
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n{_color(BOLD + 'STOA MCP Data Flow', BOLD)}")
    print(f"  Gateway : {_color(GATEWAY_URL, BOLD)}")
    print(f"  Auth    : {'Bearer <token>' if BEARER_TOKEN else _color('anonymous', YELLOW)}")
    print(f"  Timeout : {TIMEOUT}s")

    t0 = time.monotonic()

    jsonrpc_tools = test_jsonrpc_tool_listing()
    rest_tools = test_rest_tool_listing()
    test_schema_parity(jsonrpc_tools, rest_tools)
    test_rest_tool_invocation(rest_tools)
    test_response_headers()
    test_concurrent_requests()

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
