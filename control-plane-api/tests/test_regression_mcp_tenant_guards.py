"""MCP tenant isolation through production routers and real SQLite repositories."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.models.external_mcp_server import ExternalMCPServer, ExternalMCPServerTool
from src.models.tenant_tool_permission import TenantToolPermission
from src.routers import external_mcp_servers, tenant_mcp_servers, tenant_tool_permissions


@pytest.fixture
async def mcp_client() -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    app = FastAPI()
    for router in (external_mcp_servers.admin_router, tenant_mcp_servers.router, tenant_tool_permissions.router):
        app.include_router(router)
    app.state.user = User(id="fixture", email="fixture@example.invalid", username="fixture", roles=[])
    app.state.sql = []
    app.state.ids = {}

    async def identity() -> User:
        return app.state.user

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (ExternalMCPServer, ExternalMCPServerTool, TenantToolPermission):
            await connection.run_sync(model.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        for tenant in ("tenant-a", "tenant-b", None):
            server_id, permission_id = uuid4(), uuid4()
            app.state.ids[tenant] = (server_id, permission_id)
            session.add(
                ExternalMCPServer(
                    id=server_id,
                    name=f"{tenant}-marker",
                    display_name=f"{tenant}-marker",
                    base_url="https://mcp.example.invalid",
                    tenant_id=tenant,
                )
            )
            if tenant:
                session.add(
                    TenantToolPermission(
                        id=permission_id,
                        tenant_id=tenant,
                        mcp_server_id=server_id,
                        tool_name=f"{tenant}-marker",
                        allowed=False,
                        created_by="fixture",
                    )
                )
        await session.commit()

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_sql(connection, cursor, statement, parameters, context, executemany) -> None:
        app.state.sql.append(statement)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_current_user] = identity
    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test.invalid") as client:
            yield client, app
    finally:
        await engine.dispose()


def identify(app: FastAPI, role: str, tenant: str | None) -> None:
    app.state.user = User(
        id="fixture", email="fixture@example.invalid", username="fixture", roles=[role], tenant_id=tenant
    )
    app.state.sql.clear()


@pytest.mark.parametrize("role", ["cpi-admin", "tenant-admin", "devops", "viewer"])
@pytest.mark.parametrize("tenant", ["tenant-a", "tenant-b"])
@pytest.mark.parametrize("kind", ["external", "servers", "permissions"])
async def test_lists_are_scoped(mcp_client, role: str, tenant: str, kind: str) -> None:
    client, app = mcp_client
    identify(app, role, tenant)
    path = {
        "external": "/v1/admin/external-mcp-servers",
        "servers": f"/v1/tenants/{tenant}/mcp-servers",
        "permissions": f"/v1/tenants/{tenant}/tool-permissions",
    }[kind]
    response = await client.get(path, headers={"X-Tenant-ID": "forged"})
    if kind == "external" and role in ("devops", "viewer"):
        assert response.status_code == 403
        assert app.state.sql == []
        return
    assert response.status_code == 200
    items = response.json()["items" if kind == "permissions" else "servers"]
    names = {item["tool_name" if kind == "permissions" else "name"] for item in items}
    expected = {f"{tenant}-marker"}
    if kind == "external":
        expected.add("None-marker")
        if role == "cpi-admin":
            expected.update({"tenant-a-marker", "tenant-b-marker"})
    assert names == expected


@pytest.mark.parametrize("tenant", [None, "", " ", "tenant-b"])
@pytest.mark.parametrize("role", ["tenant-admin", "devops", "viewer"])
async def test_denied_scope_never_reads(mcp_client, tenant: str | None, role: str) -> None:
    client, app = mcp_client
    identify(app, role, tenant)
    server_id, permission_id = app.state.ids["tenant-a"]
    paths = [
        ("GET", "/v1/tenants/tenant-a/mcp-servers", None),
        ("GET", f"/v1/tenants/tenant-a/mcp-servers/{server_id}", None),
        (
            "POST",
            "/v1/tenants/tenant-a/mcp-servers",
            {"display_name": "New", "base_url": "https://mcp.example.invalid"},
        ),
        ("GET", "/v1/tenants/tenant-a/tool-permissions", None),
        ("DELETE", f"/v1/tenants/tenant-a/tool-permissions/{permission_id}", None),
    ]
    if tenant != "tenant-b":
        paths.extend(
            [
                ("GET", "/v1/admin/external-mcp-servers", None),
                ("GET", f"/v1/admin/external-mcp-servers/{server_id}", None),
                ("PUT", f"/v1/admin/external-mcp-servers/{server_id}", {}),
                ("DELETE", f"/v1/admin/external-mcp-servers/{server_id}", None),
                ("POST", f"/v1/admin/external-mcp-servers/{server_id}/test-connection", None),
                ("POST", f"/v1/admin/external-mcp-servers/{server_id}/sync-tools", None),
                ("GET", f"/v1/admin/external-mcp-servers/{server_id}/tools-summary", None),
                ("PATCH", f"/v1/admin/external-mcp-servers/{server_id}/tools/{permission_id}", {"enabled": True}),
            ]
        )
    for method, path, body in paths:
        response = await client.request(method, path, json=body, headers={"X-Tenant-ID": "tenant-a"})
        assert response.status_code == 403, response.text
        assert app.state.sql == []
        assert "tenant-a-marker" not in response.text


@pytest.mark.parametrize("tenant", ["tenant-a", "tenant-b"])
async def test_foreign_objects_are_refused_without_followup_queries(mcp_client, tenant: str) -> None:
    client, app = mcp_client
    identify(app, "tenant-admin", tenant)
    own_id, _ = app.state.ids[tenant]
    for path in (f"/v1/admin/external-mcp-servers/{own_id}", f"/v1/tenants/{tenant}/mcp-servers/{own_id}"):
        response = await client.get(path, headers={"X-Tenant-ID": "forged"})
        assert response.status_code == 200
        assert response.json()["name"] == f"{tenant}-marker"
    other = "tenant-b" if tenant == "tenant-a" else "tenant-a"
    server_id, permission_id = app.state.ids[other]
    for method, path, expected in [
        ("GET", f"/v1/admin/external-mcp-servers/{server_id}", 403),
        ("GET", f"/v1/tenants/{tenant}/mcp-servers/{server_id}", 404),
        ("DELETE", f"/v1/tenants/{tenant}/tool-permissions/{permission_id}", 404),
    ]:
        app.state.sql.clear()
        response = await client.request(method, path)
        assert response.status_code == expected
        assert len(app.state.sql) == (1 if method == "DELETE" else 2)
        assert all(statement.startswith("SELECT") for statement in app.state.sql)
        assert f"{other}-marker" not in response.text


@pytest.mark.parametrize("target", ["tenant-b", None, "", " "])
async def test_external_create_refuses_foreign_or_missing_target(mcp_client, target: str | None) -> None:
    client, app = mcp_client
    identify(app, "tenant-admin", "tenant-a")
    response = await client.post(
        "/v1/admin/external-mcp-servers",
        json={
            "name": "new",
            "display_name": "New",
            "base_url": "https://mcp.example.invalid",
            "tenant_id": target,
        },
        headers={"X-Tenant-ID": target or "tenant-a"},
    )
    assert response.status_code == 403
    assert app.state.sql == []


async def test_admin_without_claim_keeps_explicit_and_global_access(mcp_client) -> None:
    client, app = mcp_client
    identify(app, "cpi-admin", None)
    for tenant in ("tenant-a", "tenant-b", None):
        server_id, _ = app.state.ids[tenant]
        response = await client.get(f"/v1/admin/external-mcp-servers/{server_id}")
        assert response.status_code == 200
    for tenant in ("tenant-a", "tenant-b"):
        response = await client.get(f"/v1/tenants/{tenant}/mcp-servers")
        assert response.status_code == 200
        assert {item["name"] for item in response.json()["servers"]} == {f"{tenant}-marker"}
