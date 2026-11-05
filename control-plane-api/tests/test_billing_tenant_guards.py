"""Exercise billing tenant guards through real routers and SQLite repositories."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.models.consumer import Consumer
from src.models.department_budget import DepartmentBudget
from src.models.plan import Plan
from src.models.quota_usage import QuotaUsage
from src.models.subscription import Subscription
from src.routers import billing, consumers, plans, quotas

ROUTERS = [billing.router, consumers.router, plans.router, quotas.router]
PATHS = ["/v1/tenants/{tenant}/budgets", "/v1/consumers/{tenant}", "/v1/plans/{tenant}", "/v1/admin/quotas/{tenant}"]


@pytest.fixture
async def billing_app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    metadata = MetaData()
    for model in [Consumer, DepartmentBudget, Plan, QuotaUsage, Subscription]:
        model.__table__.to_metadata(metadata)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        for tenant in ["tenant-a", "tenant-b"]:
            consumer_id = uuid4()
            session.add(
                Consumer(
                    id=consumer_id, external_id=tenant, name=tenant, email="fixture@example.invalid", tenant_id=tenant
                )
            )
            session.add(Plan(slug=tenant, name=tenant, tenant_id=tenant))
            session.add(
                DepartmentBudget(tenant_id=tenant, department_id=tenant, period_start=datetime(2026, 1, 1, tzinfo=UTC))
            )
            session.add(
                QuotaUsage(
                    consumer_id=consumer_id,
                    tenant_id=tenant,
                    period_start_daily=datetime.now(UTC).date(),
                    period_start_monthly=datetime.now(UTC).date().replace(day=1),
                )
            )
        await session.commit()
    statements = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    app = FastAPI()
    for router in ROUTERS:
        app.include_router(router)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture.invalid") as client:
            yield app, client, statements
    finally:
        await engine.dispose()


def identify(app: FastAPI, role: str, tenant: str | None) -> None:
    async def current_user() -> User:
        return User(id="fixture", email="fixture@example.invalid", username="fixture", roles=[role], tenant_id=tenant)

    app.dependency_overrides[get_current_user] = current_user


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("role", ["cpi-admin", "tenant-admin", "devops", "viewer"])
@pytest.mark.parametrize("tenant", ["tenant-a", "tenant-b", None, "", " "])
async def test_billing_tenant_matrix(billing_app, path, role, tenant):
    app, client, statements = billing_app
    identify(app, role, tenant)
    for target in ["tenant-a", "tenant-b", " "]:
        allowed = bool(target.strip()) and (role == "cpi-admin" or target == tenant)
        allowed &= "/admin/quotas/" not in path or role in ["cpi-admin", "tenant-admin"]
        statements.clear()
        response = await client.get(path.format(tenant=target), headers={"X-Tenant-ID": "tenant-b"})
        if allowed:
            assert response.status_code == 200
            assert statements
            assert len(response.json()["items"]) == 1
            assert response.json()["items"][0]["tenant_id"] == target
        else:
            assert response.status_code == 403
            assert statements == []


@pytest.mark.parametrize("tenant", ["tenant-b", None])
async def test_every_billing_route_denies_before_read(billing_app, tenant):
    app, client, statements = billing_app
    identify(app, "tenant-admin", tenant)
    body = {
        "external_id": "fixture",
        "name": "Fixture",
        "email": "fixture@example.invalid",
        "slug": "fixture",
        "department_id": "fixture",
        "budget_limit_microcents": 1,
        "period_start": "2026-01-01T00:00:00",
        "certificate_pem": "synthetic-invalid-certificate",
        "subject_token": "synthetic-invalid-token",
        "consumer_ids": [str(uuid4())],
    }
    for router in ROUTERS:
        for route in router.routes:
            path = route.path.format(
                tenant_id="tenant-a", consumer_id=uuid4(), budget_id=uuid4(), plan_id=uuid4(), slug="fixture"
            )
            for method in route.methods:
                statements.clear()
                options = (
                    {"files": {"file": ("fixture.csv", b"external_id,name,email\n")}}
                    if path.endswith("/bulk")
                    else {"json": body}
                )
                response = await client.request(method, path, headers={"X-Tenant-ID": "tenant-a"}, **options)
                assert response.status_code == 403, (method, path, response.text)
                assert statements == []


@pytest.mark.parametrize("path", PATHS)
async def test_billing_header_alone_is_not_identity(billing_app, path):
    _, client, statements = billing_app
    response = await client.get(path.format(tenant="tenant-a"), headers={"X-Tenant-ID": "tenant-a"})
    assert response.status_code == 401
    assert statements == []


@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_billing_foreign_budget_is_hidden_and_unchanged(billing_app, method):
    app, client, statements = billing_app
    identify(app, "tenant-admin", "tenant-b")
    response = await client.get("/v1/tenants/tenant-b/budgets")
    budget = response.json()["items"][0]
    identify(app, "tenant-admin", "tenant-a")
    statements.clear()
    response = await client.request(
        method, f"/v1/tenants/tenant-a/budgets/{budget['id']}", json={"department_name": "changed"}
    )
    assert response.status_code == 404
    assert statements
    if method == "PUT":
        assert len(statements) == 1
        where = statements[0].partition("WHERE")[2]
        assert "department_budgets.id =" in where
        assert "department_budgets.tenant_id =" in where
    else:
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    identify(app, "tenant-admin", "tenant-b")
    response = await client.get(f"/v1/tenants/tenant-b/budgets/{budget['id']}")
    assert response.json()["department_name"] == budget["department_name"]
