"""CAB-2612 proofs for the explicit-allow gate introduced by #3125.

Rows live in a process-local SQLite database. The gateway hop is replaced so
these tests never open a network or a real control-plane deployment.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.models.tenant_tool_permission import TenantToolPermission
from src.routers.mcp_proxy import router, security
from src.routers.tenant_tool_permissions import _permission_cache, check_tool_allowed


def _user(role: str, tenant_id: str | None) -> User:
    return User(id="user-1", email="user@example.test", username="user", roles=[role], tenant_id=tenant_id)


def _permission(tenant: str, server: uuid.UUID, tool: str, allowed: bool) -> TenantToolPermission:
    return TenantToolPermission(
        tenant_id=tenant,
        mcp_server_id=server,
        tool_name=tool,
        allowed=allowed,
        created_by="cab-2612",
    )


@pytest.fixture(autouse=True)
async def _clear_permission_cache() -> AsyncIterator[None]:
    await _permission_cache.clear()
    yield
    await _permission_cache.clear()


async def test_deny_wins_across_cache_and_tenants() -> None:
    """Cold and hot decisions agree, a deny beats another server's allow, and expiry reloads."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    server_a = uuid.uuid4()
    server_b = uuid.uuid4()
    allow_a = _permission(tenant_a, server_a, "shared", True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(TenantToolPermission.__table__.create)
        async with AsyncSession(engine) as db:
            db.add(allow_a)
            db.add(_permission(tenant_a, server_b, "shared", False))
            db.add(_permission(tenant_a, server_a, "only_a", True))
            db.add(_permission(tenant_b, server_a, "only_b", True))
            await db.commit()

            for _ in range(2):
                assert await check_tool_allowed(tenant_a, "shared", db) is False
                assert await check_tool_allowed(tenant_a, "shared", db, server_a) is True
                assert await check_tool_allowed(tenant_a, "shared", db, server_b) is False
                assert await check_tool_allowed(tenant_a, "only_b", db) is False
                assert await check_tool_allowed(tenant_b, "only_a", db) is False
                assert await check_tool_allowed(tenant_b, "only_b", db) is True
                assert await check_tool_allowed(tenant_a, "missing", db) is False

            allow_a.allowed = False
            await db.commit()
            # The hot cache still holds the previous allow. Expiry must not keep it.
            assert await check_tool_allowed(tenant_a, "shared", db, server_a) is True
            cached = _permission_cache._cache[f"tenant:{tenant_a}"]
            # TTLCache compares naive utcnow values, so the forced expiry uses the same clock.
            cached.expires_at = datetime(2000, 1, 1)  # noqa: DTZ001
            assert await check_tool_allowed(tenant_a, "shared", db, server_a) is False
    finally:
        await _permission_cache.clear()
        await engine.dispose()


async def test_blank_tenant_is_denied_even_with_an_allow_row() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(TenantToolPermission.__table__.create)
        async with AsyncSession(engine) as db:
            db.add(_permission("", uuid.uuid4(), "shared", True))
            db.add(_permission("   ", uuid.uuid4(), "shared", True))
            await db.commit()
            assert await check_tool_allowed("", "shared", db) is False
            assert await check_tool_allowed("   ", "shared", db) is False
            assert await check_tool_allowed("tenant-a", "shared", db) is False
    finally:
        await engine.dispose()


async def test_invoke_allow_deny_and_missing_tenant(tmp_path: Path) -> None:
    """Authorized and denied invokes use the real decision, including a missing tenant."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/authz.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    server = uuid.uuid4()
    other = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.run_sync(TenantToolPermission.__table__.create)
    async with sessions() as db:
        db.add(_permission("tenant-a", server, "echo", True))
        db.add(_permission("tenant-a", server, "mixed", True))
        db.add(_permission("tenant-a", other, "mixed", False))
        db.add(_permission("tenant-b", server, "only_b", True))
        db.add(_permission("default", server, "echo", True))
        await db.commit()

    app = FastAPI()
    app.include_router(router)

    async def session() -> AsyncIterator[AsyncSession]:
        async with sessions() as connection:
            yield connection

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[security] = lambda: HTTPAuthorizationCredentials(scheme="Bearer", credentials="fixture")

    def authenticate(role: str, tenant_id: str | None) -> None:
        app.dependency_overrides[get_current_user] = lambda: _user(role, tenant_id)

    try:
        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as proxy:
            proxy.return_value = {"content": [{"type": "text", "text": "ok"}], "isError": False}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

                async def invoke(tool: str) -> int:
                    response = await client.post(f"/v1/mcp/tools/{tool}/invoke", json={"arguments": {}})
                    return response.status_code

                authenticate("tenant-admin", "tenant-a")
                assert await invoke("echo") == 200
                assert await invoke("mixed") == 403
                assert await invoke("only_b") == 403
                assert await invoke("missing") == 403

                authenticate("tenant-admin", "tenant-b")
                assert await invoke("only_b") == 200
                assert await invoke("echo") == 403

                authenticate("viewer", None)
                assert await invoke("echo") == 403
                authenticate("cpi-admin", None)
                assert await invoke("echo") == 403
                authenticate("cpi-admin", "   ")
                assert await invoke("echo") == 403
                authenticate("cpi-admin", "tenant-a")
                assert await invoke("echo") == 200

        assert proxy.await_count == 3
    finally:
        await _permission_cache.clear()
        await engine.dispose()
