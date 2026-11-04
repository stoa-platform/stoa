"""Subscription authorization through real ASGI routes and SQLite repositories."""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.models.subscription import Subscription
from src.routers.subscriptions import _has_tenant_access, _has_tenant_admin_access, router

Isolation = tuple[AsyncClient, User, list[str], list[UUID]]


@pytest.fixture
async def isolated() -> AsyncIterator[Isolation]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Subscription.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ids = [uuid4() for _ in range(4)]
    async with sessions() as session:
        for index, (tenant, owner) in enumerate([("a", "owner"), ("b", "owner"), ("a", "other"), ("b", "other")]):
            session.add(
                Subscription(
                    id=ids[index],
                    tenant_id=tenant,
                    subscriber_id=owner,
                    subscriber_email="owner@example.invalid",
                    application_id=str(uuid4()),
                    application_name="App",
                    api_id="api",
                    api_name="API",
                    api_version="1",
                )
            )
        await session.commit()
    statements: list[str] = []
    event.listen(engine.sync_engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    user = User(id="owner", email="owner@example.invalid", username="owner", tenant_id="a", roles=["viewer"])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test.invalid") as client:
        client.headers["X-Tenant-ID"] = "b"
        yield client, user, statements, ids
    await engine.dispose()


@pytest.mark.parametrize("tenant", ["a", "b"])
@pytest.mark.parametrize("role,total", [("viewer", 1), ("devops", 1), ("tenant-admin", 2), ("cpi-admin", 4)])
async def test_regression_personal_list_scope(isolated: Isolation, role: str, total: int, tenant: str) -> None:
    client, user, _, _ = isolated
    user.roles = [role]
    user.tenant_id = None if role == "cpi-admin" else tenant
    response = await client.get("/v1/subscriptions/my")
    assert response.status_code == 200
    assert response.json()["total"] == total
    if role != "cpi-admin":
        assert {item["tenant_id"] for item in response.json()["items"]} == {tenant}


@pytest.mark.parametrize("tenant,foreign", [("a", "b"), ("b", "a")])
@pytest.mark.parametrize("suffix", ["", "/pending", "/stats"])
async def test_regression_tenant_lists_are_bounded(isolated: Isolation, suffix: str, tenant: str, foreign: str) -> None:
    client, user, statements, _ = isolated
    user.tenant_id = tenant
    response = await client.get(f"/v1/subscriptions/tenant/{tenant}{suffix}")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    statements.clear()
    assert (await client.get(f"/v1/subscriptions/tenant/{foreign}{suffix}")).status_code == 403
    assert statements == []


@pytest.mark.parametrize("tenant,index", [("a", 1), ("b", 0)])
@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("GET", "", None),
        ("GET", "/rotation-info", None),
        ("DELETE", "", None),
        ("POST", "/rotate-key", {}),
        ("PATCH", "/ttl", {"extend_days": 7, "reason": "Testing"}),
        ("POST", "/approve", {}),
        ("POST", "/revoke", {"reason": "Denied"}),
        ("POST", "/suspend", {}),
        ("POST", "/reactivate", {}),
        ("POST", "/reject", {"reason": "Denied"}),
        ("POST", "/bulk", {"action": "reject", "reason": "Denied"}),
    ],
)
async def test_regression_foreign_objects_refuse_before_further_io(
    isolated: Isolation,
    method: str,
    suffix: str,
    payload: dict[str, object] | None,
    tenant: str,
    index: int,
    missing: bool,
) -> None:
    client, user, statements, ids = isolated
    user.roles = ["tenant-admin"]
    user.tenant_id = None if missing else tenant
    path = f"/{ids[index]}{suffix}" if suffix != "/bulk" else suffix
    if suffix == "/bulk":
        payload = {**(payload or {}), "ids": [str(ids[index])]}
    response = await client.request(method, f"/v1/subscriptions{path}", json=payload)
    if missing:
        assert response.status_code == 403 and statements == []
        return
    assert response.status_code == (200 if suffix == "/bulk" else 403)
    if suffix == "/bulk":
        assert response.json()["succeeded"] == 0 and len(response.json()["failed"]) == 1
    assert len(statements) == 1 and statements[0].startswith("SELECT")
    assert "owner@example.invalid" not in response.text


@pytest.mark.parametrize("tenant", [None, "", " "])
@pytest.mark.parametrize("path", ["/my", "/tenant/a", "/tenant/a/pending", "/tenant/a/stats", "/{id}"])
async def test_regression_missing_tenant_refuses_before_read(
    isolated: Isolation, path: str, tenant: str | None
) -> None:
    client, user, statements, ids = isolated
    user.tenant_id = tenant
    response = await client.get("/v1/subscriptions" + path.format(id=ids[0]))
    assert response.status_code == 403
    assert statements == []


@pytest.mark.parametrize("tenant", [None, "a"])
async def test_regression_creation_refuses_foreign_or_missing_tenant_before_io(
    isolated: Isolation, tenant: str | None
) -> None:
    client, user, statements, _ = isolated
    user.tenant_id = tenant
    response = await client.post(
        "/v1/subscriptions",
        json={
            "tenant_id": "b",
            "application_id": str(uuid4()),
            "application_name": "App",
            "api_id": "api",
            "api_name": "API",
            "api_version": "1",
        },
    )
    assert response.status_code == 403
    assert statements == []


@pytest.mark.parametrize("role", ["viewer", "devops"])
async def test_regression_role_and_cancellation_ownership_are_preserved(isolated: Isolation, role: str) -> None:
    client, user, statements, ids = isolated
    user.roles = [role]
    assert (await client.post(f"/v1/subscriptions/{ids[0]}/approve", json={})).status_code == 403
    assert (await client.delete(f"/v1/subscriptions/{ids[2]}")).status_code == 403
    assert all(statement.startswith("SELECT") for statement in statements)
    assert (await client.get(f"/v1/subscriptions/{ids[0]}")).status_code == 200
    assert (await client.get(f"/v1/subscriptions/{ids[0]}/rotation-info")).status_code == 200
    assert (await client.delete(f"/v1/subscriptions/{ids[0]}")).status_code == 204
    assert any(statement.startswith("UPDATE") for statement in statements)


async def test_regression_absent_authentication_is_rejected() -> None:
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test.invalid") as client:
        assert (await client.get("/v1/subscriptions/my", headers={"X-Tenant-ID": "a"})).status_code == 401


@pytest.mark.parametrize("role", ["viewer", "tenant-admin", "cpi-admin"])
@pytest.mark.parametrize("target", ["", " "])
def test_regression_empty_resource_target_fails_closed(role: str, target: str) -> None:
    user = User(id="owner", email="owner@example.invalid", username="owner", tenant_id="a", roles=[role])
    for guard in [_has_tenant_access, _has_tenant_admin_access]:
        assert guard(user, target) is False
