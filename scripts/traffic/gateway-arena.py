#!/usr/bin/env python3
"""Gateway Arena — Continuous Comparative Benchmarking.

Measures latency, availability, and burst resilience across multiple API gateways
(STOA, Kong, Gravitee) and pushes metrics to Prometheus Pushgateway.

Uses a local echo backend (nginx returning static JSON in <1ms) on each VPS
so benchmarks measure pure gateway overhead, not backend/network latency.

HTTP keepalive: uses requests.Session with connection pooling (pool_maxsize=200)
to reuse TCP connections across requests. This eliminates TCP handshake overhead
and measures pure gateway processing time — matching real-world API client behavior.

Warm-up: 5 sequential requests before scenarios to establish TCP connections and
warm up gateway internal caches/pools.

Scenarios:
  1. health          — single health check (availability)
  2. proxy_sequential — 20 sequential requests (base overhead P50/P95)
  3. burst_10        — 10 concurrent requests (light load)
  4. burst_50        — 50 concurrent requests (production load)
  5. burst_100       — 100 concurrent requests (stress test — Rust shines here)
  6. sustained       — 100 sequential requests (consistency/jitter)

Env vars:
  GATEWAYS          — JSON array of gateway configs
  PUSHGATEWAY_URL   — Pushgateway URL (default: http://pushgateway.monitoring.svc:9091)
  BURST_SIZES       — Comma-separated burst sizes (default: 10,50,100)
  PROXY_REPEAT      — Sequential requests count (default: 20)
  SUSTAINED_COUNT   — Sustained scenario count (default: 100)
  TIMEOUT           — Request timeout in seconds (default: 5)
  WARMUP_COUNT      — Warm-up requests per gateway (default: 5)
"""

import json
import logging
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("gateway-arena")

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    log.error("requests library not found. Install: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_GATEWAYS = json.dumps([
    {
        "name": "stoa",
        "health": "http://51.83.45.13:8080/health",
        "proxy": "http://51.83.45.13:8080/echo/get",
    },
    {
        "name": "kong",
        "health": "http://51.83.45.13:8001/status",
        "proxy": "http://51.83.45.13:8000/echo/get",
    },
    {
        "name": "gravitee",
        "health": "http://54.36.209.237:8083/management/organizations/DEFAULT/environments/DEFAULT",
        "proxy": "http://54.36.209.237:8082/echo/get",
    },
])

GATEWAYS = json.loads(os.getenv("GATEWAYS", DEFAULT_GATEWAYS))
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://pushgateway.monitoring.svc:9091")
BURST_SIZES = [int(x) for x in os.getenv("BURST_SIZES", "10,50,100").split(",")]
PROXY_REPEAT = int(os.getenv("PROXY_REPEAT", "20"))
SUSTAINED_COUNT = int(os.getenv("SUSTAINED_COUNT", "100"))
TIMEOUT = int(os.getenv("TIMEOUT", "5"))
WARMUP_COUNT = int(os.getenv("WARMUP_COUNT", "5"))


# ---------------------------------------------------------------------------
# HTTP Session with connection pooling (keepalive)
# ---------------------------------------------------------------------------
def create_session():
    """Create a requests.Session with large connection pool for burst tests.

    pool_connections: number of connection pools to cache (per host)
    pool_maxsize: max connections per host (must cover burst_100)
    """
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=200)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# ---------------------------------------------------------------------------
# Metric collection (plain dict — pushed via Pushgateway text format)
# ---------------------------------------------------------------------------
class MetricStore:
    """Collects metrics and formats them for Pushgateway."""

    def __init__(self):
        self.lines = []
        self._declared = set()

    def _declare(self, name, metric_type, help_text=""):
        if name not in self._declared:
            self._declared.add(name)
            if help_text:
                self.lines.append(f"# HELP {name} {help_text}")
            self.lines.append(f"# TYPE {name} {metric_type}")

    def histogram(self, name, labels, values, help_text=""):
        if not values:
            return
        self._declare(name, "histogram", help_text)
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        buckets = [0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
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
        self.lines.append(f"{name}{{{label_str}}} {value:.4f}")

    def push(self, url, job="gateway_arena"):
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
# Benchmark primitives
# ---------------------------------------------------------------------------
def timed_request(session, url, headers=None, timeout=TIMEOUT):
    """Make a request using a keepalive session. Returns (latency_seconds, status_code, ok)."""
    start = time.monotonic()
    try:
        resp = session.get(url, headers=headers or {}, timeout=timeout)
        elapsed = time.monotonic() - start
        return elapsed, resp.status_code, resp.status_code < 500
    except requests.exceptions.Timeout:
        return time.monotonic() - start, 0, False
    except requests.exceptions.ConnectionError:
        return time.monotonic() - start, 0, False


def warm_up(session, gw, count):
    """Send warm-up requests to establish TCP connections and warm gateway caches."""
    headers = gw.get("proxy_headers", {})
    ok = 0
    for _ in range(count):
        _, _, success = timed_request(session, gw["proxy"], headers=headers)
        if success:
            ok += 1
    log.info(f"Warm-up: {ok}/{count} OK for {gw['name']}")


def percentile(values, pct):
    """Compute percentile from a sorted or unsorted list."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(len(s) * pct / 100), len(s) - 1)
    return s[idx]


# ---------------------------------------------------------------------------
# Scenarios (all use keepalive session)
# ---------------------------------------------------------------------------
def scenario_health(session, gw):
    """Single health check — availability baseline."""
    latency, status, ok = timed_request(session, gw["health"])
    return {"scenario": "health", "latencies": [latency], "ok_count": 1 if ok else 0, "total": 1}


def scenario_proxy_sequential(session, gw, count):
    """Sequential proxy requests — measures base gateway overhead (P50/P95)."""
    latencies, ok_count = [], 0
    headers = gw.get("proxy_headers", {})
    for _ in range(count):
        latency, _, ok = timed_request(session, gw["proxy"], headers=headers)
        latencies.append(latency)
        if ok:
            ok_count += 1
    return {"scenario": "proxy_sequential", "latencies": latencies, "ok_count": ok_count, "total": count}


def scenario_burst(session, gw, size):
    """Concurrent burst — measures resilience under concurrent load.

    requests.Session is thread-safe for connection pooling. Each thread reuses
    connections from the shared pool, matching real-world load balancer behavior.
    """
    latencies, ok_count = [], 0
    headers = gw.get("proxy_headers", {})
    with ThreadPoolExecutor(max_workers=size) as pool:
        futures = [pool.submit(timed_request, session, gw["proxy"], headers) for _ in range(size)]
        for future in as_completed(futures):
            latency, _, ok = future.result()
            latencies.append(latency)
            if ok:
                ok_count += 1
    return {"scenario": f"burst_{size}", "latencies": latencies, "ok_count": ok_count, "total": size}


def scenario_sustained(session, gw, count):
    """Sustained sequential load — measures consistency (jitter = GC pauses, thread contention)."""
    latencies, ok_count = [], 0
    headers = gw.get("proxy_headers", {})
    for _ in range(count):
        latency, _, ok = timed_request(session, gw["proxy"], headers=headers)
        latencies.append(latency)
        if ok:
            ok_count += 1
    return {"scenario": "sustained", "latencies": latencies, "ok_count": ok_count, "total": count}


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------
def compute_score(all_results):
    """Compute composite Arena Score (0-100).

    Weights tuned for gateway overhead differentiation:
      - 15% base overhead (proxy_sequential P95)
      - 25% burst_50 P95 (production load)
      - 25% burst_100 P95 (stress — where async runtimes diverge)
      - 15% availability (across all scenarios)
      - 10% error rate
      - 10% consistency (sustained jitter — GC-free = lower jitter)

    Caps tightened for keepalive benchmarking (TCP reuse eliminates handshake overhead):
      - base: 200ms (was 500ms — sequential with keepalive should be <50ms)
      - burst_50: 1000ms (was 3000ms — pool reuse, no connection storm)
      - burst_100: 2000ms (was 5000ms — same logic, larger scale)
    """
    # Collect per-scenario stats
    scenario_map = {}
    total_ok = 0
    total_requests = 0
    for r in all_results:
        scenario_map[r["scenario"]] = r
        total_ok += r["ok_count"]
        total_requests += r["total"]

    if total_requests == 0:
        return 0.0

    def latency_score(scenario_name, cap_seconds=0.5):
        """Score a scenario's P95: 100 = instant, 0 = at/above cap."""
        r = scenario_map.get(scenario_name)
        if not r or not r["latencies"]:
            return 50.0  # neutral if missing
        p95 = percentile(r["latencies"], 95)
        return max(0, 100 * (1 - p95 / cap_seconds))

    # Caps tuned for keepalive benchmarking (K8s → VPS, TCP reuse).
    # Tighter than raw-TCP caps because keepalive eliminates connection storms.
    base_score = latency_score("proxy_sequential", 0.2)
    burst50_score = latency_score("burst_50", 1.0)
    burst100_score = latency_score("burst_100", 2.0)

    # Availability
    availability_score = 100 * (total_ok / total_requests)

    # Error rate
    error_score = 100 * (total_ok / total_requests)

    # Consistency — coefficient of variation of sustained latencies
    sustained = scenario_map.get("sustained")
    if sustained and len(sustained["latencies"]) > 1:
        mean_lat = statistics.mean(sustained["latencies"])
        if mean_lat > 0:
            cv = statistics.stdev(sustained["latencies"]) / mean_lat
            consistency_score = max(0, 100 * (1 - cv))
        else:
            consistency_score = 100.0
    else:
        consistency_score = 100.0

    score = (
        0.15 * base_score
        + 0.25 * burst50_score
        + 0.25 * burst100_score
        + 0.15 * availability_score
        + 0.10 * error_score
        + 0.10 * consistency_score
    )
    return round(min(100, max(0, score)), 2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    log.info(json.dumps({
        "event": "config",
        "gateways": len(GATEWAYS),
        "burst_sizes": BURST_SIZES,
        "proxy_repeat": PROXY_REPEAT,
        "sustained_count": SUSTAINED_COUNT,
        "warmup_count": WARMUP_COUNT,
        "keepalive": True,
    }))
    metrics = MetricStore()
    results_summary = []

    for gw in GATEWAYS:
        name = gw["name"]
        log.info(f"Benchmarking gateway: {name}")

        # Create a keepalive session per gateway (connection pool reused across scenarios)
        session = create_session()

        # Warm-up: establish TCP connections before measuring
        warm_up(session, gw, WARMUP_COUNT)

        gw_results = []

        # Run all scenarios
        scenarios = [
            lambda: scenario_health(session, gw),
            lambda: scenario_proxy_sequential(session, gw, PROXY_REPEAT),
        ]
        for bs in BURST_SIZES:
            scenarios.append((lambda s: lambda: scenario_burst(session, gw, s))(bs))
        scenarios.append(lambda: scenario_sustained(session, gw, SUSTAINED_COUNT))

        for scenario_fn in scenarios:
            result = scenario_fn()
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

            # Per-scenario stats
            p50 = percentile(result["latencies"], 50) * 1000
            p95 = percentile(result["latencies"], 95) * 1000
            p99 = percentile(result["latencies"], 99) * 1000
            log.info(json.dumps({
                "gateway": name,
                "scenario": scenario,
                "ok": ok,
                "fail": fail,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
            }))

            # Record percentile gauges for Grafana
            metrics.gauge("gateway_arena_p50_seconds", {"gateway": name, "scenario": scenario}, p50 / 1000, "P50 latency")
            metrics.gauge("gateway_arena_p95_seconds", {"gateway": name, "scenario": scenario}, p95 / 1000, "P95 latency")
            metrics.gauge("gateway_arena_p99_seconds", {"gateway": name, "scenario": scenario}, p99 / 1000, "P99 latency")

        # Close session after all scenarios for this gateway
        session.close()

        # Composite score
        score = compute_score(gw_results)
        health_ok = gw_results[0]["ok_count"] / gw_results[0]["total"] if gw_results[0]["total"] > 0 else 0
        metrics.gauge("gateway_arena_score", {"gateway": name}, score, "Composite arena score 0-100")
        metrics.gauge("gateway_arena_availability", {"gateway": name}, health_ok, "Gateway availability 0-1")

        results_summary.append({"gateway": name, "score": score, "availability": health_ok})
        log.info(f"Gateway {name}: score={score}, availability={health_ok:.2f}")

    # Push to Pushgateway
    metrics.push(PUSHGATEWAY_URL)

    # Leaderboard
    leaderboard = sorted(results_summary, key=lambda x: x["score"], reverse=True)
    log.info(json.dumps({"event": "leaderboard", "ranking": leaderboard, "timestamp": datetime.now(timezone.utc).isoformat()}))

    return 0


if __name__ == "__main__":
    sys.exit(run())
