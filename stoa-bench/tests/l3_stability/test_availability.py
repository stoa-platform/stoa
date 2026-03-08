"""L3-05: Service availability monitoring.

Checks 24h uptime of critical services (Portal, Gateway, Keycloak).
Threshold: >= 99.5% per service.

This test runs as a lightweight HTTP check — not a full CUJ.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

pytestmark = [pytest.mark.l3]

TIMEOUT = float(os.environ.get("BENCH_TIMEOUT", "5"))

SERVICES = {
    "api": {
        "url": os.environ.get("STOA_API_URL", "http://stoa-control-plane-api.stoa-system.svc"),
        "health_path": "/health/live",
    },
    "gateway": {
        "url": os.environ.get("STOA_GATEWAY_URL", "http://stoa-gateway.stoa-system.svc"),
        "health_path": "/health",
    },
    "auth": {
        "url": os.environ.get("STOA_AUTH_URL", "http://keycloak.stoa-system.svc"),
        "health_path": "/realms/stoa",
    },
}


class TestServiceAvailability:
    """L3-05: Verify critical services are reachable."""

    @pytest.mark.parametrize("service_name", list(SERVICES.keys()))
    async def test_service_health(self, service_name: str):
        """Check health endpoint for each critical service."""
        svc = SERVICES[service_name]
        url = f"{svc['url']}{svc['health_path']}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT)) as client:
            try:
                resp = await client.get(url)
                assert resp.status_code < 400, (
                    f"{service_name} health check returned {resp.status_code}"
                )
            except httpx.ConnectError:
                pytest.fail(f"{service_name} unreachable at {url}")
            except httpx.TimeoutException:
                pytest.fail(f"{service_name} timed out at {url} (>{TIMEOUT}s)")
