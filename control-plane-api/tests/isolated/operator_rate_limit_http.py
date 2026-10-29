"""Real operator auth and native HTTP quota on the MCP catalogue.

Only catalogue data/DB are simulated, as in test_mcp_router.py. The main app,
auth dependency, route decorator, key function, fixed-window engine and 429
handler remain real. No lifespan or external service is started.
This file is invoked explicitly in its dedicated CP CI pytest process; its
filename intentionally excludes it from the ordinary shared-process collection.
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from limits.storage import MemoryStorage, memory as memory_storage
from limits.strategies import FixedWindowRateLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user, security
from src.config import settings
from src.database import get_db
from src.middleware.rate_limit import limiter
from src.routers.mcp import MCPServerRepository


@pytest.mark.asyncio
async def test_operator_http_quota_is_enforced_per_key(
    app: FastAPI, mock_db_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A/B each get 100 requests; exhausted A never consumes B's quota."""
    assert app.state.limiter is limiter
    assert limiter.enabled
    assert limiter._auto_check
    assert not limiter._storage_dead
    assert isinstance(limiter._storage, MemoryStorage)
    assert isinstance(limiter.limiter, FixedWindowRateLimiter)
    assert get_current_user not in app.dependency_overrides
    assert security not in app.dependency_overrides

    # This is the existing route's declared 100/minute, never a test-only limit.
    quota = 100
    route = "/v1/mcp/servers"
    key_a = "synthetic-operator-a"
    key_b = "synthetic-operator-b"
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", f"{key_a},{key_b}")
    monkeypatch.setattr(settings, "STOA_DISABLE_AUTH", False)

    async def catalogue_db() -> AsyncIterator[AsyncSession]:
        yield mock_db_session

    monkeypatch.setitem(app.dependency_overrides, get_db, catalogue_db)
    read_catalogue = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(MCPServerRepository, "list_visible_for_user", read_catalogue)

    # All MemoryStorage instances share this module clock: use a dedicated process.
    # Fresh counters stay local to this case; process/event-loop clocks remain real.
    clock = [2_000_000_000.0]
    monkeypatch.setattr(memory_storage, "time", SimpleNamespace(time=lambda: clock[0]))
    storage = MemoryStorage()
    monkeypatch.setattr(limiter, "_storage", storage)
    monkeypatch.setattr(limiter, "_limiter", FixedWindowRateLimiter(storage))

    async def assert_unauthenticated(client: AsyncClient) -> None:
        previous_reads = read_catalogue.await_count
        for headers in ({}, {"X-Operator-Key": "synthetic-unconfigured-key"}):
            response = await client.get(route, headers=headers)
            assert response.status_code == 401
            assert response.json()["detail"] == "Not authenticated"
        assert read_catalogue.await_count == previous_reads

    async def consume_and_exhaust(client: AsyncClient, key: str, previous_reads: int) -> None:
        for _ in range(quota):
            response = await client.get(route, headers={"X-Operator-Key": key})
            assert response.status_code == 200
            assert response.json() == {"servers": [], "total_count": 0}
        assert read_catalogue.await_count == previous_reads + quota
        response = await client.get(route, headers={"X-Operator-Key": key})
        assert response.status_code == 429
        assert response.json()["error"] == "rate_limit_exceeded"
        assert response.json()["retry_after_seconds"] == 60
        assert response.headers["Retry-After"] == "60"
        assert read_catalogue.await_count == previous_reads + quota

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await assert_unauthenticated(client)
            await consume_and_exhaust(client, key_a, 0)
            await assert_unauthenticated(client)
            await consume_and_exhaust(client, key_b, quota)
            await assert_unauthenticated(client)
            read_catalogue.assert_awaited_with(
                user_roles=["cpi-admin"], tenant_id=None, category=None, page=1, page_size=20
            )

            # Real expiry, no sleep and no counter reset between the HTTP phases.
            clock[0] += 60
            for key in (key_a, key_b):
                response = await client.get(route, headers={"X-Operator-Key": key})
                assert response.status_code == 200
                assert response.json() == {"servers": [], "total_count": 0}
            assert read_catalogue.await_count == 2 * quota + 2
            mock_db_session.execute.assert_not_awaited()
    finally:
        storage.timer.cancel()
        storage.timer.join(timeout=1)
        storage.reset()
