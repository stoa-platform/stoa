#!/usr/bin/env python3
"""Seed error snapshot data for the Error Correlation demo (CAB-550).

Generates controlled API errors with unique trace_ids for correlation
in OpenSearch dashboards.

Usage:
    python seed-error-snapshot.py --api-url https://api.gostoa.dev --dry-run
    python seed-error-snapshot.py --api-url https://api.gostoa.dev --execute
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def generate_trace_id() -> str:
    """Generate a unique trace ID."""
    return str(uuid.uuid4())


def make_request(
    url: str,
    method: str = "GET",
    data: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> tuple[int, str]:
    """Make an HTTP request and return (status_code, body).

    Returns the status code even on HTTP errors (4xx, 5xx).
    """
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=req_headers, method=method)

    try:
        with urlopen(req, timeout=timeout) as resp:
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
            "data": {"invalid_field": True},  # Missing required fields
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
            "headers": {"X-Request-Timeout": "1"},  # Force timeout
            "expected_status": 504,
        },
    ]


def print_scenario(scenario: dict, index: int) -> None:
    """Print scenario details."""
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
    # Any 4xx or 5xx is a "successful" error generation
    is_error = status >= 400
    match_str = "MATCH" if status == expected else f"EXPECTED {expected}"
    print(f"  Result:      HTTP {status} ({match_str})")

    if is_error:
        # Truncate long bodies
        preview = body[:200] + "..." if len(body) > 200 else body
        print(f"  Error body:  {preview}")

    return is_error


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Seed error snapshot data for STOA Error Correlation demo"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the Control Plane API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print scenarios without executing (default mode)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the scenarios (send actual HTTP requests)",
    )
    args = parser.parse_args()

    if not args.execute:
        args.dry_run = True

    api_url = args.api_url.rstrip("/")
    scenarios = build_error_scenarios(api_url)
    timestamp = datetime.now(timezone.utc).isoformat()

    print(f"STOA Error Snapshot Seed — CAB-550")
    print(f"Timestamp: {timestamp}")
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
        print("\nRe-run with --execute to send requests.")
        return

    print("\n[EXECUTE] — Sending requests...\n")
    results: list[bool] = []
    for i, scenario in enumerate(scenarios):
        success = execute_scenario(scenario, i)
        results.append(success)

    # Summary
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
