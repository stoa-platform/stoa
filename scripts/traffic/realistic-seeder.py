#!/usr/bin/env python3
"""Realistic Traffic Seeder — generates multi-mode, multi-auth API traffic.

Produces realistic OTel traces across 3+ deployment modes (Gateway, Link,
Connect) with 5 auth tiers for the Call Flow Dashboard demo.

Usage:
    # K8s (edge-mcp mode only)
    python realistic-seeder.py

    # VPS (sidecar + connect modes)
    python realistic-seeder.py --mode vps

    # Edge-only for safe demo fallback
    python realistic-seeder.py --mode edge-only

    # Include webMethods traffic via stoa-connect
    python realistic-seeder.py --include-webmethods

    # Dry run (no actual requests)
    python realistic-seeder.py --dry-run

Environment variables:
    GATEWAY_URL          - Base URL for edge-mcp gateway (default: http://stoa-gateway.stoa-system.svc:80)
    SIDECAR_URL          - Base URL for sidecar gateway (default: http://stoa-gateway-sidecar:80)
    CONNECT_URL          - Base URL for stoa-connect (default: http://stoa-connect:8090)
    CONNECT_WM_URL       - Base URL for stoa-connect → webMethods (default: http://stoa-connect-wm:8090)
    KC_TOKEN_URL         - Keycloak token endpoint
    KC_CLIENT_ID         - OAuth2 client ID
    KC_CLIENT_SECRET     - OAuth2 client secret
    OPENWEATHERMAP_API_KEY - OpenWeatherMap API key
    NEWSAPI_KEY          - NewsAPI API key
    ALPHAVANTAGE_KEY     - Alpha Vantage API key
    DPOP_SIGNING_KEY     - JWK private key for DPoP proofs (JSON)
    MTLS_CLIENT_CERT     - Path to mTLS client certificate
    MTLS_CLIENT_KEY      - Path to mTLS client key
    DURATION             - Total run duration in seconds (default: 480)
    TENANTS              - Comma-separated tenant IDs (default: high-five,oasis,ioi)
    BUSINESS_HOURS_MULT  - Multiplier during CET business hours (default: 3.0)
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

# Add parent dir to path for sibling imports when run from scripts/traffic/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.traffic.auth_helpers import apply_auth, setup_mtls_session
from scripts.traffic.scenarios import (
    MODE_REQUEST_COUNTS,
    MODE_REQUEST_COUNTS_EDGE_ONLY,
    MODE_WEIGHTS,
    MODE_WEIGHTS_EDGE_ONLY,
    SCENARIOS,
    WEBMETHODS_APIS,
    ApiTarget,
    Scenario,
    get_apis_for_mode,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("traffic-seeder")


def get_config() -> dict:
    """Build configuration from environment variables."""
    return {
        "gateway_url": os.environ.get("GATEWAY_URL", "http://stoa-gateway.stoa-system.svc:80"),
        "sidecar_url": os.environ.get("SIDECAR_URL", "http://stoa-gateway-sidecar:80"),
        "connect_url": os.environ.get("CONNECT_URL", "http://stoa-connect:8090"),
        "connect_wm_url": os.environ.get("CONNECT_WM_URL", "http://stoa-connect-wm:8090"),
        "duration": int(os.environ.get("DURATION", "480")),
        "tenants": os.environ.get("TENANTS", "high-five,oasis,ioi").split(","),
        "business_hours_mult": float(os.environ.get("BUSINESS_HOURS_MULT", "3.0")),
    }


def get_base_url(mode: str, config: dict) -> str:
    """Return base URL for a given deployment mode."""
    return {
        "edge-mcp": config["gateway_url"],
        "sidecar": config["sidecar_url"],
        "connect": config["connect_url"],
        "connect-wm": config["connect_wm_url"],
    }.get(mode, config["gateway_url"])


# ---------------------------------------------------------------------------
# Time-of-Day Awareness
# ---------------------------------------------------------------------------


def is_business_hours() -> bool:
    """Check if current time is within CET business hours (08:00-18:00)."""
    now_utc = datetime.now(timezone.utc)
    cet_hour = (now_utc.hour + 1) % 24  # CET = UTC+1 (simplified, ignores DST)
    return 8 <= cet_hour <= 18


def get_rate_multiplier(config: dict) -> float:
    """Return request rate multiplier based on time of day."""
    if is_business_hours():
        return config["business_hours_mult"]
    return 1.0


# ---------------------------------------------------------------------------
# Scenario Selection
# ---------------------------------------------------------------------------


def pick_scenario() -> Scenario:
    """Select a scenario using weighted random choice."""
    weights = [s.weight for s in SCENARIOS]
    return random.choices(SCENARIOS, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Request Execution
# ---------------------------------------------------------------------------


class Metrics:
    """Request metrics tracker with mode × auth cross-tabulation."""

    def __init__(self) -> None:
        self.total = 0
        self.success = 0
        self.errors = 0
        self.by_mode: dict[str, dict[str, int]] = {}
        self.by_auth: dict[str, dict[str, int]] = {}
        self.by_mode_auth: dict[str, dict[str, dict[str, int]]] = {}
        self.by_status: dict[int, int] = {}
        self.latencies: list[float] = []

    def record(self, mode: str, auth_type: str, status: int, latency_ms: float) -> None:
        self.total += 1
        is_ok = 200 <= status < 400
        if is_ok:
            self.success += 1
        else:
            self.errors += 1

        self.by_mode.setdefault(mode, {"ok": 0, "err": 0})
        self.by_mode[mode]["ok" if is_ok else "err"] += 1

        self.by_auth.setdefault(auth_type, {"ok": 0, "err": 0})
        self.by_auth[auth_type]["ok" if is_ok else "err"] += 1

        # Cross-tab: mode × auth_type
        self.by_mode_auth.setdefault(mode, {})
        self.by_mode_auth[mode].setdefault(auth_type, {"ok": 0, "err": 0})
        self.by_mode_auth[mode][auth_type]["ok" if is_ok else "err"] += 1

        self.by_status[status] = self.by_status.get(status, 0) + 1
        self.latencies.append(latency_ms)

    def summary(self) -> dict:
        p50 = sorted(self.latencies)[len(self.latencies) // 2] if self.latencies else 0
        return {
            "total": self.total,
            "success": self.success,
            "errors": self.errors,
            "success_rate": round(self.success / max(self.total, 1) * 100, 1),
            "p50_ms": round(p50, 1),
            "by_mode": self.by_mode,
            "by_auth": self.by_auth,
            "by_mode_auth": self.by_mode_auth,
            "by_status": self.by_status,
        }


def execute_request(
    session: requests.Session,
    api: ApiTarget,
    mode: str,
    config: dict,
    scenario: Scenario,
    metrics: Metrics,
    dry_run: bool = False,
) -> None:
    """Execute a single API request with auth and error injection."""
    base_url = get_base_url(mode, config)
    url = f"{base_url}{api.url_path}"
    method = random.choice(api.methods)
    tenant = random.choice(config["tenants"])

    # Build headers
    headers = {
        "X-Tenant-ID": tenant,
        "X-Stoa-Deployment-Mode": mode,
        "X-Stoa-Seeder": "realistic-v1",
        "User-Agent": f"stoa-traffic-seeder/1.0 ({mode})",
    }
    params = dict(api.query_params)

    # Error injection
    if scenario.error_injection and api.error_injectable and random.random() < scenario.error_rate:
        error_code = random.choice(scenario.error_codes)
        headers["X-Simulate-Error"] = str(error_code)

    # Apply auth
    try:
        auth_headers, auth_params = apply_auth(
            session, api.name, api.auth_type, url, method, headers, params
        )
        headers.update(auth_headers)
        params.update(auth_params)
    except Exception:
        logger.debug("Auth application failed for %s, proceeding without auth", api.name)

    if dry_run:
        logger.info(
            "[DRY-RUN] %s %s mode=%s auth=%s tenant=%s",
            method, url, mode, api.auth_type, tenant,
        )
        metrics.record(mode, api.auth_type, 200, api.expected_latency_ms)
        return

    try:
        start = time.monotonic()
        resp = session.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            timeout=(10, 30),
        )
        latency_ms = (time.monotonic() - start) * 1000

        metrics.record(mode, api.auth_type, resp.status_code, latency_ms)

        log_fn = logger.info if resp.status_code < 400 else logger.warning
        log_fn(
            "%s %s → %d (%.0fms) mode=%s auth=%s tenant=%s",
            method, api.name, resp.status_code, latency_ms, mode, api.auth_type, tenant,
        )

    except requests.exceptions.Timeout:
        metrics.record(mode, api.auth_type, 504, 30000)
        logger.warning("TIMEOUT %s %s mode=%s", method, api.name, mode)
    except requests.exceptions.ConnectionError:
        metrics.record(mode, api.auth_type, 503, 0)
        logger.warning("CONN_ERROR %s %s mode=%s — continuing", method, api.name, mode)
    except Exception:
        metrics.record(mode, api.auth_type, 500, 0)
        logger.warning("ERROR %s %s mode=%s", method, api.name, mode, exc_info=True)


# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------


def _build_mode_request_counts(mode_weights: dict[str, float], args: argparse.Namespace) -> dict[str, tuple[int, int]]:
    """Return per-mode (min, max) request count ranges for the active modes."""
    base = MODE_REQUEST_COUNTS_EDGE_ONLY if args.mode == "edge-only" else MODE_REQUEST_COUNTS
    counts: dict[str, tuple[int, int]] = {}
    for mode in mode_weights:
        counts[mode] = base.get(mode, (5, 20))
    return counts


def _roll_mode_counts(count_ranges: dict[str, tuple[int, int]]) -> dict[str, int]:
    """Roll a random request count for each mode for this scenario cycle."""
    return {mode: random.randint(lo, hi) for mode, (lo, hi) in count_ranges.items()}


def _print_cross_tab(summary: dict) -> None:
    """Print a human-readable mode × auth cross-tabulation table."""
    cross = summary.get("by_mode_auth", {})
    if not cross:
        return

    # Collect all auth types across modes
    all_auth = sorted({auth for auths in cross.values() for auth in auths})
    modes = sorted(cross.keys())

    # Header
    col_w = 14
    header = f"{'mode':<14}" + "".join(f"{a:>{col_w}}" for a in all_auth) + f"{'TOTAL':>{col_w}}"
    logger.info("── mode × auth ─────────────────────────────────────")
    logger.info(header)
    logger.info("─" * len(header))

    for mode in modes:
        row_total = 0
        cells = []
        for auth in all_auth:
            counts = cross[mode].get(auth, {"ok": 0, "err": 0})
            total = counts["ok"] + counts["err"]
            row_total += total
            cell = f"{counts['ok']}/{total}" if total > 0 else "—"
            cells.append(f"{cell:>{col_w}}")
        logger.info(f"{mode:<14}" + "".join(cells) + f"{row_total:>{col_w}}")

    # Footer: totals per auth
    footer_cells = []
    grand = 0
    for auth in all_auth:
        auth_total = sum(
            cross[m].get(auth, {"ok": 0, "err": 0})["ok"] + cross[m].get(auth, {"ok": 0, "err": 0})["err"]
            for m in modes
        )
        grand += auth_total
        footer_cells.append(f"{auth_total:>{col_w}}")
    logger.info("─" * len(header))
    logger.info(f"{'TOTAL':<14}" + "".join(footer_cells) + f"{grand:>{col_w}}")


def run_seeder(args: argparse.Namespace) -> int:
    """Main seeder loop — runs for DURATION seconds with random counts per mode."""
    config = get_config()
    metrics = Metrics()

    # Determine mode weights
    if args.mode == "edge-only":
        mode_weights = MODE_WEIGHTS_EDGE_ONLY
    elif args.mode == "vps":
        # VPS mode: sidecar + connect only
        mode_weights = {"sidecar": 0.55, "connect": 0.45}
        if args.include_webmethods:
            mode_weights = {"sidecar": 0.40, "connect": 0.30, "connect-wm": 0.30}
    else:
        mode_weights = dict(MODE_WEIGHTS)
        if not args.include_webmethods and "connect-wm" in mode_weights:
            # Redistribute connect-wm weight
            wm_weight = mode_weights.pop("connect-wm", 0)
            for k in mode_weights:
                mode_weights[k] += wm_weight / len(mode_weights)

    count_ranges = _build_mode_request_counts(mode_weights, args)

    # Setup mTLS session (if certs available)
    mtls_session = setup_mtls_session(
        os.environ.get("MTLS_CLIENT_CERT"),
        os.environ.get("MTLS_CLIENT_KEY"),
    )

    # Default session with connection pooling
    default_session = requests.Session()
    default_session.timeout = (10, 30)

    duration = config["duration"]
    start_time = time.monotonic()
    rate_mult = get_rate_multiplier(config)

    logger.info(
        "Starting realistic traffic seeder: duration=%ds mode=%s modes=%s include_wm=%s rate_mult=%.1fx",
        duration, args.mode, list(mode_weights.keys()), args.include_webmethods, rate_mult,
    )
    logger.info(
        "Request count ranges per mode: %s",
        {m: f"{lo}-{hi}" for m, (lo, hi) in count_ranges.items()},
    )

    cycle_num = 0

    while (time.monotonic() - start_time) < duration:
        # New scenario cycle: pick scenario + roll random counts per mode
        current_scenario = pick_scenario()
        mode_counts = _roll_mode_counts(count_ranges)
        cycle_num += 1

        total_cycle = sum(mode_counts.values())
        logger.info(
            "Cycle %d — scenario=%s counts=%s (total=%d, %.0f req/s)",
            cycle_num, current_scenario.name, mode_counts, total_cycle,
            current_scenario.requests_per_second,
        )

        # Build a shuffled request list: each entry is a mode
        request_queue: list[str] = []
        for mode, count in mode_counts.items():
            request_queue.extend([mode] * count)
        random.shuffle(request_queue)

        for mode in request_queue:
            if (time.monotonic() - start_time) >= duration:
                break

            # Pick API for this mode
            apis = get_apis_for_mode(mode)
            if not apis and mode == "connect-wm" and args.include_webmethods:
                apis = WEBMETHODS_APIS
            if not apis:
                mode = "edge-mcp"
                apis = get_apis_for_mode(mode)

            if current_scenario.name == "auth_variety":
                auth_types = list({a.auth_type for a in apis})
                target_auth = random.choice(auth_types)
                candidates = [a for a in apis if a.auth_type == target_auth]
                api = random.choice(candidates)
            else:
                api = random.choice(apis)

            # Choose session (mTLS for fapi_advanced, default for others)
            session = mtls_session if (api.auth_type == "fapi_advanced" and mtls_session) else default_session

            # Execute
            execute_request(session, api, mode, config, current_scenario, metrics, dry_run=args.dry_run)

            # Rate control with jitter
            effective_rps = current_scenario.requests_per_second * rate_mult
            sleep_time = 1.0 / max(effective_rps, 0.1)
            sleep_time *= random.uniform(0.8, 1.2)
            time.sleep(sleep_time)

    # Final report
    summary = metrics.summary()
    logger.info("Seeder complete: %s", json.dumps(summary, indent=2))
    _print_cross_tab(summary)

    # Exit code: 1 if error rate > 50% (alerts operators)
    if summary["success_rate"] < 50:
        logger.error("Error rate too high: %.1f%% — check gateway/backend health", 100 - summary["success_rate"])
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="STOA Realistic Traffic Seeder")
    parser.add_argument(
        "--mode",
        choices=["k8s", "vps", "edge-only"],
        default="k8s",
        help="Deployment context: k8s (all modes), vps (sidecar+connect), edge-only (safe demo fallback)",
    )
    parser.add_argument(
        "--include-webmethods",
        action="store_true",
        help="Include webMethods traffic via stoa-connect (requires connect-wm endpoint)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log requests without sending them",
    )
    args = parser.parse_args()
    sys.exit(run_seeder(args))


if __name__ == "__main__":
    main()
