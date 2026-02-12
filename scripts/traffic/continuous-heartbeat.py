#!/usr/bin/env python3
"""STOA Continuous Traffic Generator — Lightweight heartbeat for Grafana dashboards.

Hits public health/metrics/portal endpoints at configurable rate.
No auth tokens needed (read-only public endpoints only).

Env vars:
  GATEWAY_URL   — Gateway base URL (default: http://stoa-gateway:8080)
  API_URL       — Control Plane API URL (default: http://control-plane-api:8000)
  PORTAL_URL    — Portal URL (default: http://stoa-portal:8080)
  DURATION      — Run duration in seconds (default: 600)
  RATE          — Requests per second (default: 0.2)
  TENANTS       — Comma-separated tenant IDs for header rotation (default: high-five,oasis,ioi)
"""

import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("traffic-gen")

try:
    import requests
except ImportError:
    log.error("requests library not found. Install: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://stoa-gateway:8080")
API_URL = os.getenv("API_URL", "http://control-plane-api:8000")
PORTAL_URL = os.getenv("PORTAL_URL", "http://stoa-portal:8080")
DURATION = int(os.getenv("DURATION", "600"))
RATE = float(os.getenv("RATE", "0.2"))
TENANTS = os.getenv("TENANTS", "high-five,oasis,ioi").split(",")
TIMEOUT = 10  # request timeout in seconds

# Endpoints to hit (method, url, description)
ENDPOINTS = [
    ("GET", f"{GATEWAY_URL}/health", "gateway-health"),
    ("GET", f"{GATEWAY_URL}/metrics", "gateway-metrics"),
    ("GET", f"{GATEWAY_URL}/mcp/health", "mcp-health"),
    ("GET", f"{API_URL}/health", "api-health"),
    ("GET", f"{API_URL}/api/v1/portal/apis", "portal-apis"),
]


def make_request(method: str, url: str, name: str, tenant: str) -> dict:
    """Make a single HTTP request and return result dict."""
    headers = {
        "X-Tenant-ID": tenant,
        "User-Agent": "stoa-traffic-gen/1.0",
    }
    start = time.monotonic()
    try:
        resp = requests.request(method, url, headers=headers, timeout=TIMEOUT)
        elapsed = time.monotonic() - start
        return {
            "name": name,
            "status": resp.status_code,
            "duration_ms": round(elapsed * 1000, 1),
            "tenant": tenant,
            "ok": resp.status_code < 500,
        }
    except requests.exceptions.Timeout:
        elapsed = time.monotonic() - start
        return {
            "name": name,
            "status": 0,
            "duration_ms": round(elapsed * 1000, 1),
            "tenant": tenant,
            "ok": False,
            "error": "timeout",
        }
    except requests.exceptions.ConnectionError:
        elapsed = time.monotonic() - start
        return {
            "name": name,
            "status": 0,
            "duration_ms": round(elapsed * 1000, 1),
            "tenant": tenant,
            "ok": False,
            "error": "connection_error",
        }


def run() -> int:
    """Main traffic generation loop. Returns exit code."""
    interval = 1.0 / RATE if RATE > 0 else 5.0
    end_time = time.monotonic() + DURATION
    total = 0
    errors = 0

    log.info(
        f"Starting traffic generator: {len(ENDPOINTS)} endpoints, "
        f"rate={RATE} req/s, duration={DURATION}s, tenants={TENANTS}"
    )

    while time.monotonic() < end_time:
        # Pick random endpoint and tenant
        method, url, name = random.choice(ENDPOINTS)
        tenant = random.choice(TENANTS)

        result = make_request(method, url, name, tenant)
        total += 1
        if not result["ok"]:
            errors += 1

        log.info(json.dumps(result))

        # Jitter: 80% to 120% of base interval
        jitter = interval * random.uniform(0.8, 1.2)
        remaining = end_time - time.monotonic()
        if remaining > 0:
            time.sleep(min(jitter, remaining))

    error_rate = (errors / total * 100) if total > 0 else 0
    summary = {
        "event": "summary",
        "total_requests": total,
        "errors": errors,
        "error_rate_pct": round(error_rate, 1),
        "duration_secs": DURATION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    log.info(json.dumps(summary))

    # Exit 1 if error rate > 50%
    if error_rate > 50:
        log.error(f"HIGH ERROR RATE: {error_rate:.1f}% ({errors}/{total})")
        return 1

    log.info(f"SUCCESS: {total} requests, {error_rate:.1f}% errors")
    return 0


if __name__ == "__main__":
    sys.exit(run())
