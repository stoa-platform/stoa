#!/usr/bin/env python3
"""Seed error snapshot data for the Error Correlation demo (CAB-550).

Generates controlled API errors with unique trace_ids for correlation
in OpenSearch dashboards. Two modes:

1. --execute: Send HTTP requests to the API to trigger real errors
2. --seed-opensearch: Index sample error documents directly into OpenSearch

Usage:
    python seed-error-snapshot.py --dry-run
    python seed-error-snapshot.py --execute --api-url http://localhost:8000
    python seed-error-snapshot.py --seed-opensearch --opensearch-url https://localhost:9200
"""

from __future__ import annotations

import argparse
import json
import random
import ssl
import sys
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TENANTS = ["oasis", "oasis-gunters", "acme-corp", "demo-org-alpha"]
ERROR_TYPES = [
    "validation_error",
    "authentication_error",
    "rate_limit_exceeded",
    "upstream_timeout",
    "internal_error",
    "tool_not_found",
    "contract_violation",
]
ENDPOINTS = [
    "/v1/tenants",
    "/v1/portal/apis",
    "/v1/consumers",
    "/mcp/v1/tools/invoke",
    "/v1/admin/catalog/seed",
    "/v1/subscriptions",
    "/mcp/v1/errors/snapshots",
]
METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
SEVERITIES = ["critical", "error", "warning"]


def generate_trace_id() -> str:
    return str(uuid.uuid4())


def _ssl_context() -> ssl.SSLContext:
    """Unverified SSL context for demo OpenSearch with self-signed certs."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def make_request(
    url: str,
    method: str = "GET",
    data: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
    use_ssl_noverify: bool = False,
) -> tuple[int, str]:
    """Make an HTTP request and return (status_code, body)."""
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=req_headers, method=method)

    ctx = _ssl_context() if use_ssl_noverify else None
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()
    except URLError as e:
        return 0, str(e.reason)


def build_error_scenarios(api_url: str) -> list[dict]:
    """Build the 3 error scenarios for the demo."""
    return [
        {
            "name": "400 Bad Request — Invalid Payload",
            "description": "Send a malformed request body to trigger validation error",
            "trace_id": generate_trace_id(),
            "url": f"{api_url}/v1/tenants",
            "method": "POST",
            "data": {"invalid_field": True},
            "headers": {},
            "expected_status": 400,
        },
        {
            "name": "500 Internal Server Error — Backend Failure",
            "description": "Call an endpoint that triggers a server-side error",
            "trace_id": generate_trace_id(),
            "url": f"{api_url}/v1/admin/catalog/seed",
            "method": "POST",
            "data": {"force": True, "nonexistent_option": True},
            "headers": {},
            "expected_status": 500,
        },
        {
            "name": "504 Gateway Timeout — Slow Upstream",
            "description": "Call a proxied endpoint with a very short timeout",
            "trace_id": generate_trace_id(),
            "url": f"{api_url}/v1/portal/apis",
            "method": "GET",
            "data": None,
            "headers": {"X-Request-Timeout": "1"},
            "expected_status": 504,
        },
    ]


def build_opensearch_documents(count: int = 50) -> list[dict]:
    """Build sample error snapshot documents for OpenSearch indexing."""
    now = datetime.now(timezone.utc)
    docs = []

    for i in range(count):
        # Spread errors over the last 24 hours
        ts = now - timedelta(minutes=random.randint(1, 1440))
        error_type = random.choice(ERROR_TYPES)
        http_status = _status_for_type(error_type)
        tenant = random.choice(TENANTS)
        endpoint = random.choice(ENDPOINTS)
        method = random.choice(METHODS)
        severity = _severity_for_status(http_status)

        doc = {
            "@timestamp": ts.isoformat(),
            "trace_id": generate_trace_id(),
            "tenant_id": tenant,
            "error_type": error_type,
            "error_message": _message_for_type(error_type, endpoint),
            "http_status": http_status,
            "method": method,
            "endpoint": endpoint,
            "severity": severity,
            "resolution_status": random.choice(["unresolved", "investigating", "resolved", "ignored"]),
            "user_agent": random.choice([
                "Claude/3.5 (MCP Agent)",
                "stoactl/1.0",
                "Mozilla/5.0 (Portal)",
                "curl/8.4.0",
            ]),
            "response_time_ms": random.randint(50, 30000) if error_type == "upstream_timeout" else random.randint(5, 500),
            "request_id": generate_trace_id(),
        }
        docs.append(doc)

    return docs


def _status_for_type(error_type: str) -> int:
    return {
        "validation_error": 400,
        "authentication_error": 401,
        "rate_limit_exceeded": 429,
        "upstream_timeout": 504,
        "internal_error": 500,
        "tool_not_found": 404,
        "contract_violation": 422,
    }.get(error_type, 500)


def _severity_for_status(status: int) -> str:
    if status >= 500:
        return "critical"
    if status == 429:
        return "warning"
    return "error"


def _message_for_type(error_type: str, endpoint: str) -> str:
    messages = {
        "validation_error": f"Request body validation failed for {endpoint}: missing required field 'name'",
        "authentication_error": f"JWT token expired or invalid for {endpoint}",
        "rate_limit_exceeded": f"Rate limit exceeded: 100 requests/min for tenant on {endpoint}",
        "upstream_timeout": f"Upstream did not respond within 30s for {endpoint}",
        "internal_error": f"Unexpected error processing request to {endpoint}: NoneType has no attribute 'id'",
        "tool_not_found": f"MCP tool not found: requested tool does not exist in catalog for {endpoint}",
        "contract_violation": f"Response does not match UAC contract schema for {endpoint}",
    }
    return messages.get(error_type, f"Unknown error on {endpoint}")


def index_to_opensearch(opensearch_url: str, docs: list[dict], auth: str) -> int:
    """Index error documents into OpenSearch using bulk API. Returns count indexed."""
    user, password = auth.split(":", 1) if ":" in auth else (auth, auth)
    index_name = f"stoa-errors-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"

    # Build NDJSON bulk body
    bulk_lines: list[str] = []
    for doc in docs:
        action = json.dumps({"index": {"_index": index_name}})
        bulk_lines.append(action)
        bulk_lines.append(json.dumps(doc))
    bulk_body = "\n".join(bulk_lines) + "\n"

    import base64

    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {
        "Content-Type": "application/x-ndjson",
        "Authorization": f"Basic {credentials}",
    }

    req = Request(
        f"{opensearch_url}/_bulk",
        data=bulk_body.encode(),
        headers=headers,
        method="POST",
    )
    ctx = _ssl_context()
    try:
        with urlopen(req, timeout=30, context=ctx) as resp:
            result = json.loads(resp.read().decode())
            if result.get("errors"):
                failed = sum(1 for item in result["items"] if "error" in item.get("index", {}))
                print(f"  Warning: {failed} documents failed to index")
                return len(docs) - failed
            return len(docs)
    except (HTTPError, URLError) as e:
        error_msg = e.read().decode() if isinstance(e, HTTPError) else str(e.reason)
        print(f"  Error indexing to OpenSearch: {error_msg[:200]}")
        return 0


def print_scenario(scenario: dict, index: int) -> None:
    print(f"\n--- Scenario {index + 1}: {scenario['name']} ---")
    print(f"  Description: {scenario['description']}")
    print(f"  Trace ID:    {scenario['trace_id']}")
    print(f"  URL:         {scenario['method']} {scenario['url']}")
    if scenario["data"]:
        print(f"  Body:        {json.dumps(scenario['data'])}")
    print(f"  Expected:    HTTP {scenario['expected_status']}")


def execute_scenario(scenario: dict, index: int) -> bool:
    """Execute a single error scenario. Returns True if error was generated."""
    print_scenario(scenario, index)

    headers = dict(scenario["headers"])
    headers["X-Trace-Id"] = scenario["trace_id"]
    headers["X-Request-Id"] = scenario["trace_id"]

    status, body = make_request(
        url=scenario["url"],
        method=scenario["method"],
        data=scenario["data"],
        headers=headers,
    )

    if status == 0:
        print(f"  Result:      CONNECTION ERROR — {body}")
        return False

    expected = scenario["expected_status"]
    is_error = status >= 400
    match_str = "MATCH" if status == expected else f"EXPECTED {expected}"
    print(f"  Result:      HTTP {status} ({match_str})")

    if is_error:
        preview = body[:200] + "..." if len(body) > 200 else body
        print(f"  Error body:  {preview}")

    return is_error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed error snapshot data for STOA Error Correlation demo"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the Control Plane API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--opensearch-url",
        default="https://localhost:9200",
        help="OpenSearch URL (default: https://localhost:9200)",
    )
    parser.add_argument(
        "--opensearch-auth",
        default="admin:admin",
        help="OpenSearch auth as user:password (default: admin:admin)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of sample errors to generate for --seed-opensearch (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print scenarios without executing (default mode)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the scenarios (send actual HTTP requests to API)",
    )
    parser.add_argument(
        "--seed-opensearch",
        action="store_true",
        help="Index sample error documents directly into OpenSearch",
    )
    args = parser.parse_args()

    if not args.execute and not args.seed_opensearch:
        args.dry_run = True

    timestamp = datetime.now(timezone.utc).isoformat()
    print("STOA Error Snapshot Seed — CAB-550")
    print(f"Timestamp: {timestamp}")

    if args.seed_opensearch:
        print(f"Target:    {args.opensearch_url}")
        print(f"Mode:      SEED OPENSEARCH ({args.count} documents)")
        print()

        docs = build_opensearch_documents(args.count)

        # Show sample
        print(f"Sample document:")
        print(f"  {json.dumps(docs[0], indent=2)[:300]}...")
        print()

        indexed = index_to_opensearch(args.opensearch_url, docs, args.opensearch_auth)
        print(f"\nIndexed {indexed}/{len(docs)} error snapshots into OpenSearch")

        if indexed > 0:
            index_name = f"stoa-errors-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"
            print(f"Index:     {index_name}")
            print(f"Dashboard: http://localhost:3001/d/stoa-error-snapshots/stoa-error-snapshots")
            print(f"OpenSearch Dashboards: http://localhost:5601/app/discover")
        else:
            print("No documents indexed. Check OpenSearch connectivity.")
            sys.exit(1)
        return

    api_url = args.api_url.rstrip("/")
    scenarios = build_error_scenarios(api_url)

    print(f"Target:    {api_url}")
    print(f"Mode:      {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Scenarios: {len(scenarios)}")

    if args.dry_run:
        print("\n[DRY RUN] — No requests will be sent.\n")
        for i, scenario in enumerate(scenarios):
            print_scenario(scenario, i)
        print("\n--- Trace IDs for OpenSearch lookup ---")
        for scenario in scenarios:
            print(f"  {scenario['trace_id']}  ({scenario['name']})")
        print("\nRe-run with --execute to send requests or --seed-opensearch to index directly.")
        return

    print("\n[EXECUTE] — Sending requests...\n")
    results: list[bool] = []
    for i, scenario in enumerate(scenarios):
        success = execute_scenario(scenario, i)
        results.append(success)

    errors_generated = sum(results)
    print(f"\n{'=' * 60}")
    print(f"Summary: {errors_generated}/{len(scenarios)} errors generated")
    print(f"\nTrace IDs for OpenSearch lookup:")
    for scenario, success in zip(scenarios, results):
        status = "OK" if success else "MISSED"
        print(f"  [{status}] {scenario['trace_id']}  ({scenario['name']})")

    if errors_generated < len(scenarios):
        print(f"\nWarning: {len(scenarios) - errors_generated} scenario(s) did not produce expected errors.")
        print("Check API connectivity and endpoint availability.")
        sys.exit(1)


if __name__ == "__main__":
    main()
