# Copyright 2026 CAB Ingénierie — Apache 2.0
"""STOA Control Plane API — Locust benchmark suite.

Scenarios cover the 5 critical endpoint groups:
  1. Health (baseline)
  2. Tenants (CRUD)
  3. API Catalog (list, search)
  4. Portal (public search)
  5. Subscriptions (lifecycle)

Usage:
  # Headless (CI)
  locust -f locustfile.py --headless -u 50 -r 10 --run-time 120s \
         --host http://localhost:8000 --csv results/bench

  # Web UI (local dev)
  locust -f locustfile.py --host http://localhost:8000
"""

import logging
import os

from locust import HttpUser, between, events, tag, task

logger = logging.getLogger(__name__)

AUTH_TOKEN = os.getenv("BENCH_AUTH_TOKEN", "")
TENANT_ID = os.getenv("BENCH_TENANT_ID", "oasis")


class STOAControlPlaneUser(HttpUser):
    """Simulates a platform operator interacting with the Control Plane API."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Set auth headers if token is available."""
        if AUTH_TOKEN:
            self.client.headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
        self.client.headers["Accept"] = "application/json"

    # ------------------------------------------------------------------ Health
    @tag("health", "baseline")
    @task(10)
    def health_live(self) -> None:
        """GET /health/live — liveness probe (baseline latency)."""
        self.client.get("/health/live", name="/health/live")

    @tag("health")
    @task(5)
    def health_ready(self) -> None:
        """GET /health/ready — readiness probe (dependency checks)."""
        self.client.get("/health/ready", name="/health/ready")

    @tag("health")
    @task(2)
    def health_startup(self) -> None:
        """GET /health/startup — startup probe."""
        self.client.get("/health/startup", name="/health/startup")

    # ----------------------------------------------------------------- Tenants
    @tag("tenants")
    @task(8)
    def tenants_list(self) -> None:
        """GET /v1/tenants — list all tenants."""
        self.client.get("/v1/tenants", name="/v1/tenants")

    @tag("tenants")
    @task(4)
    def tenant_get(self) -> None:
        """GET /v1/tenants/{id} — get single tenant."""
        self.client.get(f"/v1/tenants/{TENANT_ID}", name="/v1/tenants/[id]")

    @tag("tenants")
    @task(2)
    def tenant_usage(self) -> None:
        """GET /v1/tenants/{id}/usage — tenant resource usage."""
        self.client.get(
            f"/v1/tenants/{TENANT_ID}/usage",
            name="/v1/tenants/[id]/usage",
        )

    # ------------------------------------------------------------- API Catalog
    @tag("apis")
    @task(8)
    def apis_list(self) -> None:
        """GET /v1/tenants/{id}/apis — list APIs for tenant."""
        self.client.get(
            f"/v1/tenants/{TENANT_ID}/apis",
            name="/v1/tenants/[id]/apis",
        )

    @tag("apis")
    @task(3)
    def apis_list_paginated(self) -> None:
        """GET /v1/tenants/{id}/apis?page=1&page_size=10 — paginated."""
        self.client.get(
            f"/v1/tenants/{TENANT_ID}/apis?page=1&page_size=10",
            name="/v1/tenants/[id]/apis?paginated",
        )

    # ------------------------------------------------------------------ Portal
    @tag("portal")
    @task(8)
    def portal_apis(self) -> None:
        """GET /v1/portal/apis — portal API catalog."""
        self.client.get("/v1/portal/apis", name="/v1/portal/apis")

    @tag("portal")
    @task(5)
    def portal_search(self) -> None:
        """GET /v1/portal/apis?search=test — portal search."""
        self.client.get(
            "/v1/portal/apis?search=test",
            name="/v1/portal/apis?search",
        )

    @tag("portal")
    @task(3)
    def portal_mcp_servers(self) -> None:
        """GET /v1/portal/mcp-servers — MCP server catalog."""
        self.client.get("/v1/portal/mcp-servers", name="/v1/portal/mcp-servers")

    # ---------------------------------------------------------- Subscriptions
    @tag("subscriptions")
    @task(5)
    def subscriptions_list(self) -> None:
        """GET /v1/tenants/{id}/subscriptions — list subscriptions."""
        self.client.get(
            f"/v1/tenants/{TENANT_ID}/subscriptions",
            name="/v1/tenants/[id]/subscriptions",
        )

    # ---------------------------------------------------------- Gateway
    @tag("gateway")
    @task(3)
    def gateway_list(self) -> None:
        """GET /v1/tenants/{id}/gateways — list gateways."""
        self.client.get(
            f"/v1/tenants/{TENANT_ID}/gateways",
            name="/v1/tenants/[id]/gateways",
        )

    # ---------------------------------------------------------- Applications
    @tag("applications")
    @task(4)
    def applications_list(self) -> None:
        """GET /v1/tenants/{id}/applications — list applications."""
        self.client.get(
            f"/v1/tenants/{TENANT_ID}/applications",
            name="/v1/tenants/[id]/applications",
        )


class HealthOnlyUser(HttpUser):
    """Lightweight user that only hits health endpoints — useful for baseline benchmarks."""

    wait_time = between(0.1, 0.5)

    @tag("health", "baseline")
    @task
    def health_live(self) -> None:
        self.client.get("/health/live", name="/health/live [baseline]")


@events.quitting.add_listener
def check_thresholds(environment, **_kwargs) -> None:
    """Fail the run if p95 latency exceeds thresholds."""
    from .config import THRESHOLDS

    failures = []
    for name, _stats in environment.runner.stats.entries.items():
        entry = environment.runner.stats.entries[name]
        p95 = entry.get_response_time_percentile(0.95) or 0

        # Match threshold by endpoint pattern
        for key, threshold_ms in THRESHOLDS.items():
            if key.replace("_", "/") in name[0].lower() or key in name[0].lower():
                if p95 > threshold_ms:
                    failures.append(f"{name[0]}: p95={p95:.0f}ms > {threshold_ms}ms")
                break

    if failures:
        logger.warning("Threshold violations:\n  %s", "\n  ".join(failures))
        environment.process_exit_code = 1
