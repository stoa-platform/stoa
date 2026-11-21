"""Shared fixtures for STOA Bench tests.

Provides authenticated httpx clients, token management, and test data cleanup.
Every CUJ test is idempotent: creates bench-prefixed data, cleans up after.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration from env vars (same as bench_config.yaml but direct)
# ---------------------------------------------------------------------------

API_URL = os.environ.get("STOA_API_URL", "http://stoa-control-plane-api.stoa-system.svc")
GATEWAY_URL = os.environ.get("STOA_GATEWAY_URL", "http://stoa-gateway.stoa-system.svc")
AUTH_URL = os.environ.get("STOA_AUTH_URL", "http://keycloak.stoa-system.svc")
PORTAL_URL = os.environ.get("STOA_PORTAL_URL", "http://stoa-portal.stoa-system.svc")

KC_REALM = os.environ.get("STOA_KC_REALM", "stoa")
ADMIN_CLIENT_ID = os.environ.get("BENCH_ADMIN_CLIENT_ID", "stoa-healthcheck")
ADMIN_CLIENT_SECRET = os.environ.get("BENCH_ADMIN_CLIENT_SECRET", "")
CONSUMER_CLIENT_ID = os.environ.get("BENCH_CONSUMER_CLIENT_ID", "stoa-bench-consumer")
CONSUMER_CLIENT_SECRET = os.environ.get("BENCH_CONSUMER_CLIENT_SECRET", "")

TIMEOUT = float(os.environ.get("BENCH_TIMEOUT", "10"))
TEST_PREFIX = "bench-"


# ---------------------------------------------------------------------------
# Result collector — each CUJ sub-test appends its result here
# ---------------------------------------------------------------------------


@dataclass
class SubTestResult:
    test_id: str
    status: str  # "PASS" or "FAIL"
    latency_ms: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CUJResult:
    cuj_id: str
    sub_tests: list[SubTestResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def status(self) -> str:
        if not self.sub_tests:
            return "FAIL"
        return "PASS" if all(s.status == "PASS" for s in self.sub_tests) else "FAIL"

    @property
    def e2e_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "cuj_id": self.cuj_id,
            "status": self.status,
            "e2e_ms": round(self.e2e_ms, 1),
            "sub_tests": {
                s.test_id: {
                    "status": s.status,
                    "latency_ms": round(s.latency_ms, 1),
                    **s.details,
                }
                for s in self.sub_tests
            },
        }


# ---------------------------------------------------------------------------
# Token fetching
# ---------------------------------------------------------------------------


async def _fetch_token(
    client: httpx.AsyncClient,
    client_id: str,
    client_secret: str,
    scopes: str = "",
) -> str:
    """Get an access_token via client_credentials grant."""
    token_url = f"{AUTH_URL}/realms/{KC_REALM}/protocol/openid-connect/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scopes:
        data["scope"] = scopes

    resp = await client.post(token_url, data=data, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="module")
async def http_client():
    """Shared httpx async client for the test module."""
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT, connect=5.0),
        follow_redirects=True,
    )
    yield client
    try:
        await client.aclose()
    except Exception:
        pass  # Ignore connection pool cleanup errors in teardown


@pytest.fixture(scope="module")
async def admin_token(http_client: httpx.AsyncClient) -> str:
    """JWT token with tenant-admin / cpi-admin role."""
    if not ADMIN_CLIENT_SECRET:
        pytest.skip("BENCH_ADMIN_CLIENT_SECRET not set")
    return await _fetch_token(http_client, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET)


@pytest.fixture(scope="module")
async def consumer_token(http_client: httpx.AsyncClient) -> str:
    """JWT token with consumer / viewer role (portal access)."""
    if not CONSUMER_CLIENT_SECRET:
        pytest.skip("BENCH_CONSUMER_CLIENT_SECRET not set")
    return await _fetch_token(http_client, CONSUMER_CLIENT_ID, CONSUMER_CLIENT_SECRET)


@pytest.fixture(scope="module")
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def consumer_headers(consumer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {consumer_token}", "Content-Type": "application/json"}


@pytest.fixture()
def cuj_result(request) -> CUJResult:
    """CUJ result collector. Use request.param or marker to set cuj_id."""
    cuj_id = getattr(request, "param", None) or request.node.module.__name__.split("_")[-1]
    result = CUJResult(cuj_id=cuj_id, start_time=time.monotonic())
    yield result
    result.end_time = time.monotonic()


# ---------------------------------------------------------------------------
# Cleanup registry
# ---------------------------------------------------------------------------


@dataclass
class CleanupRegistry:
    """Track bench-created resources for cleanup."""

    subscriptions: list[str] = field(default_factory=list)
    applications: list[str] = field(default_factory=list)

    async def cleanup(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        """Delete all bench-created resources. Best-effort, never fails the test."""
        for sub_id in self.subscriptions:
            try:
                await client.delete(
                    f"{API_URL}/v1/subscriptions/{sub_id}",
                    headers=headers,
                    timeout=TIMEOUT,
                )
            except Exception:
                pass
        for app_id in self.applications:
            try:
                await client.delete(
                    f"{API_URL}/v1/portal/applications/{app_id}",
                    headers=headers,
                    timeout=TIMEOUT,
                )
            except Exception:
                pass


@pytest.fixture()
async def cleanup(http_client: httpx.AsyncClient, admin_headers: dict[str, str]):
    """Provides a CleanupRegistry that auto-cleans on test teardown."""
    registry = CleanupRegistry()
    yield registry
    await registry.cleanup(http_client, admin_headers)
