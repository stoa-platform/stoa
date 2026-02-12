#!/usr/bin/env python3
"""Gateway Arena — Continuous Comparative Benchmarking.

Measures latency, availability, and burst resilience across multiple API gateways
(STOA, Kong, Gravitee) and pushes metrics to Prometheus Pushgateway.

Inspired by Chatbot Arena (Elo), Artificial Analysis (Quality Index), HELM (holistic eval).

Env vars:
  GATEWAYS          — JSON array of gateway configs (see default below)
  PUSHGATEWAY_URL   — Pushgateway URL (default: http://pushgateway.monitoring.svc:9091)
  BURST_SIZE        — Number of concurrent requests in burst scenario (default: 10)
  PROXY_REPEAT      — Number of sequential proxy requests for P50/P95/P99 (default: 10)
  TIMEOUT           — Request timeout in seconds (default: 5)
"""

import json
import logging
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("gateway-arena")

try:
    import requests
except ImportError:
    log.error("requests library not found. Install: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_GATEWAYS = json.dumps([
    {
        "name": "stoa",
        "health": "https://mcp.gostoa.dev/health",
        "proxy": "https://mcp.gostoa.dev/v1/apis",
        "proxy_headers": {"X-Tenant-ID": "oasis"},
    },
    {
        "name": "kong",
        "health": "http://51.83.45.13:8001/status",
        "proxy": "http://51.83.45.13:8000/httpbin/get",
    },
    {
        "name": "gravitee",
        "health": "http://54.36.209.237:8083/management/organizations/DEFAULT/environments/DEFAULT",
        "proxy": "http://54.36.209.237:8082/httpbin/get",
        "proxy_headers": {"Authorization": "Basic YWRtaW46YWRtaW4="},
    },
])

GATEWAYS = json.loads(os.getenv("GATEWAYS", DEFAULT_GATEWAYS))
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://pushgateway.monitoring.svc:9091")
BURST_SIZE = int(os.getenv("BURST_SIZE", "10"))
PROXY_REPEAT = int(os.getenv("PROXY_REPEAT", "10"))
TIMEOUT = int(os.getenv("TIMEOUT", "5"))


# ---------------------------------------------------------------------------
# Metric collection (plain dict — pushed via Pushgateway text format)
# ---------------------------------------------------------------------------
class MetricStore:
    """Collects metrics and formats them for Pushgateway."""

    def __init__(self):
        self.lines = []
        self._declared = set()

    def _declare(self, name, metric_type, help_text=""):
        """Emit HELP/TYPE lines only once per metric name."""
        if name not in self._declared:
            self._declared.add(name)
            if help_text:
                self.lines.append(f"# HELP {name} {help_text}")
            self.lines.append(f"# TYPE {name} {metric_type}")

    def histogram(self, name, labels, values, help_text=""):
        """Add histogram metric from a list of observed values."""
        if not values:
            return
        self._declare(name, "histogram", help_text)
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        buckets = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        for b in buckets:
            count_le = sum(1 for v in values if v <= b)
            self.lines.append(f'{name}_bucket{{{label_str},le="{b}"}} {count_le}')
        self.lines.append(f'{name}_bucket{{{label_str},le="+Inf"}} {len(values)}')
        self.lines.append(f"{name}_sum{{{label_str}}} {sum(values):.6f}")
        self.lines.append(f"{name}_count{{{label_str}}} {len(values)}")

    def counter(self, name, labels, value, help_text=""):
        self._declare(name, "counter", help_text)
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        self.lines.append(f"{name}{{{label_str}}} {value}")

    def gauge(self, name, labels, value, help_text=""):
        self._declare(name, "gauge", help_text)
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        self.lines.append(f"{name}{{{label_str}}} {value:.2f}")

    def push(self, url, job="gateway_arena"):
        """Push all metrics to Pushgateway."""
        body = "\n".join(self.lines) + "\n"
        push_url = f"{url}/metrics/job/{job}"
        try:
            resp = requests.put(push_url, data=body, headers={"Content-Type": "text/plain"}, timeout=10)
            if resp.status_code < 300:
                log.info(f"Pushed {len(self.lines)} metric lines to {push_url}")
            else:
                log.warning(f"Pushgateway returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log.error(f"Failed to push metrics: {e}")


# ---------------------------------------------------------------------------
# Benchmark scenarios
# ---------------------------------------------------------------------------
def timed_request(url, headers=None, timeout=TIMEOUT):
    """Make a request and return (latency_seconds, status_code, ok)."""
    start = time.monotonic()
    try:
        resp = requests.get(url, headers=headers or {}, timeout=timeout)
        elapsed = time.monotonic() - start
        return elapsed, resp.status_code, resp.status_code < 500
    except requests.exceptions.Timeout:
        return time.monotonic() - start, 0, False
    except requests.exceptions.ConnectionError:
        return time.monotonic() - start, 0, False


def scenario_health(gw):
    """Scenario 1: Single health check — measures availability."""
    latency, status, ok = timed_request(gw["health"])
    return {"scenario": "health", "latencies": [latency], "statuses": [status], "ok_count": 1 if ok else 0, "total": 1}


def scenario_proxy(gw):
    """Scenario 2: Sequential proxy requests — measures P50/P95/P99."""
    latencies, statuses, ok_count = [], [], 0
    headers = gw.get("proxy_headers", {})
    for _ in range(PROXY_REPEAT):
        latency, status, ok = timed_request(gw["proxy"], headers=headers)
        latencies.append(latency)
        statuses.append(status)
        if ok:
            ok_count += 1
    return {"scenario": "proxy_passthrough", "latencies": latencies, "statuses": statuses, "ok_count": ok_count, "total": PROXY_REPEAT}


def scenario_burst(gw):
    """Scenario 3: Concurrent burst — measures resilience under load."""
    latencies, statuses, ok_count = [], [], 0
    headers = gw.get("proxy_headers", {})

    with ThreadPoolExecutor(max_workers=BURST_SIZE) as pool:
        futures = [pool.submit(timed_request, gw["proxy"], headers) for _ in range(BURST_SIZE)]
        for future in as_completed(futures):
            latency, status, ok = future.result()
            latencies.append(latency)
            statuses.append(status)
            if ok:
                ok_count += 1

    return {"scenario": "burst", "latencies": latencies, "statuses": statuses, "ok_count": ok_count, "total": BURST_SIZE}


# ---------------------------------------------------------------------------
# Composite score (Artificial Analysis inspired)
# ---------------------------------------------------------------------------
def compute_score(all_results):
    """Compute composite Arena Score (0-100) from all scenario results."""
    all_latencies = []
    total_ok = 0
    total_requests = 0

    for r in all_results:
        all_latencies.extend(r["latencies"])
        total_ok += r["ok_count"]
        total_requests += r["total"]

    if not all_latencies or total_requests == 0:
        return 0.0

    # Latency score: P95 based, 0-100 (lower is better, capped at 1s)
    sorted_lat = sorted(all_latencies)
    p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
    p95 = sorted_lat[p95_idx]
    latency_score = max(0, 100 * (1 - p95 / 1.0))

    # Availability score
    availability_score = 100 * (total_ok / total_requests)

    # Error rate score
    error_count = total_requests - total_ok
    error_score = 100 * (1 - error_count / total_requests)

    # Consistency score (lower jitter = better)
    mean_lat = statistics.mean(all_latencies)
    if mean_lat > 0 and len(all_latencies) > 1:
        stddev = statistics.stdev(all_latencies)
        consistency_score = max(0, 100 * (1 - stddev / mean_lat))
    else:
        consistency_score = 100.0

    # Weighted composite
    score = (0.40 * latency_score) + (0.30 * availability_score) + (0.20 * error_score) + (0.10 * consistency_score)
    return round(min(100, max(0, score)), 2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    log.info(f"Gateway Arena starting: {len(GATEWAYS)} gateways, burst={BURST_SIZE}, proxy_repeat={PROXY_REPEAT}")
    metrics = MetricStore()
    results_summary = []

    for gw in GATEWAYS:
        name = gw["name"]
        log.info(f"Benchmarking gateway: {name}")

        gw_results = []
        for scenario_fn in [scenario_health, scenario_proxy, scenario_burst]:
            result = scenario_fn(gw)
            gw_results.append(result)
            scenario = result["scenario"]

            # Record histogram
            metrics.histogram(
                "gateway_arena_latency_seconds",
                {"gateway": name, "scenario": scenario},
                result["latencies"],
                "Latency of gateway arena benchmark requests",
            )

            # Record request counts
            ok = result["ok_count"]
            fail = result["total"] - ok
            metrics.counter(
                "gateway_arena_requests_total",
                {"gateway": name, "scenario": scenario, "status": "200"},
                ok,
                "Total gateway arena requests by status",
            )
            if fail > 0:
                metrics.counter(
                    "gateway_arena_requests_total",
                    {"gateway": name, "scenario": scenario, "status": "error"},
                    fail,
                )

            log.info(json.dumps({
                "gateway": name,
                "scenario": scenario,
                "ok": ok,
                "fail": fail,
                "p50_ms": round(sorted(result["latencies"])[len(result["latencies"]) // 2] * 1000, 1) if result["latencies"] else 0,
            }))

        # Composite score
        score = compute_score(gw_results)
        health_ok = gw_results[0]["ok_count"] / gw_results[0]["total"] if gw_results[0]["total"] > 0 else 0
        metrics.gauge("gateway_arena_score", {"gateway": name}, score, "Composite arena score 0-100")
        metrics.gauge("gateway_arena_availability", {"gateway": name}, health_ok, "Gateway availability 0-1")

        results_summary.append({"gateway": name, "score": score, "availability": health_ok})
        log.info(f"Gateway {name}: score={score}, availability={health_ok:.2f}")

    # Push to Pushgateway
    metrics.push(PUSHGATEWAY_URL)

    # Leaderboard log
    leaderboard = sorted(results_summary, key=lambda x: x["score"], reverse=True)
    log.info(json.dumps({"event": "leaderboard", "ranking": leaderboard, "timestamp": datetime.now(timezone.utc).isoformat()}))

    return 0


if __name__ == "__main__":
    sys.exit(run())
