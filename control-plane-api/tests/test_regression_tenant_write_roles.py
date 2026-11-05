"""Regression coverage for tenant write roles and budget update scoping."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.auth import User, get_current_user
from src.auth.rbac import normalize_roles
from src.database import get_db
from src.models.consumer import Consumer
from src.models.department_budget import DepartmentBudget
from src.models.plan import Plan
from src.routers import billing, consumers, plans
from src.schemas.billing import DepartmentBudgetUpdate
from src.services.billing_service import BillingService


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (Consumer, DepartmentBudget, Plan):
            await connection.run_sync(model.__table__.create)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        yield db
    await engine.dispose()


@pytest.fixture
async def api(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    app = FastAPI()
    for router in (billing.router, consumers.router, plans.router):
        app.include_router(router)

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(
        consumers.keycloak_service, "create_consumer_client", AsyncMock(return_value={"client_id": "test"})
    )
    yield app


def set_user(app: FastAPI, role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: User(
        id="test-user",
        email="user@example.test",
        username="test-user",
        roles=normalize_roles([role]),
        tenant_id="tenant-a",
    )


RESOURCES = [
    (
        "/v1/tenants/tenant-a/budgets",
        {
            "department_id": "test",
            "budget_limit_microcents": 100,
            "period_start": "2026-01-01T00:00:00",
        },
        {"budget_limit_microcents": 200},
    ),
    (
        "/v1/consumers/tenant-a",
        {"external_id": "test", "name": "Test", "email": "user@example.test"},
        {"name": "Updated"},
    ),
    ("/v1/plans/tenant-a", {"slug": "test", "name": "Test"}, {"name": "Updated"}),
]


@pytest.mark.parametrize("path,payload,change", RESOURCES)
@pytest.mark.parametrize(
    "role,allowed",
    [
        ("viewer", False),
        ("stoa.consumer", False),
        ("stoa.security", False),
        ("stoa.agent", False),
        ("unknown", False),
        ("tenant-admin", True),
        ("cpi-admin", True),
        ("devops", True),
        ("stoa.product_owner", True),
        ("stoa.admin", True),
        ("stoa.developer", True),
    ],
)
async def test_regression_cab_2441_write_roles(
    api: FastAPI,
    path: str,
    payload: dict,
    change: dict,
    role: str,
    allowed: bool,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        set_user(api, "tenant-admin")
        seeded = await client.post(path, json=payload)
        assert seeded.status_code == 201, seeded.text
        item_path = f"{path}/{seeded.json()['id']}"
        set_user(api, role)
        created = await client.post(
            path, json={**payload, "department_id": "second", "external_id": "second", "slug": "second"}
        )
        assert created.status_code == (201 if allowed else 403), created.text
        updated = await client.put(item_path, json=change)
        assert updated.status_code == (200 if allowed else 403), updated.text
        if allowed:
            for key, value in change.items():
                assert updated.json()[key] == value
        assert (await client.get(path)).status_code == 200
        assert (await client.get(item_path)).status_code == 200
        deleted = await client.delete(item_path)
        assert deleted.status_code == (204 if allowed else 403), deleted.text
        if not allowed:
            unchanged = await client.get(item_path)
            for key in change:
                assert unchanged.json()[key] == seeded.json()[key]


@pytest.mark.parametrize("role", ["tenant-admin", "cpi-admin", "stoa.product_owner", "devops"])
async def test_regression_cab_2441_cross_tenant_budget_update(
    api: FastAPI,
    session: AsyncSession,
    role: str,
) -> None:
    budget = DepartmentBudget(
        tenant_id="tenant-b",
        department_id="test",
        budget_limit_microcents=100,
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(budget)
    await session.commit()
    set_user(api, role)
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.put(
            f"/v1/tenants/tenant-a/budgets/{budget.id}",
            json={"budget_limit_microcents": 200},
        )
        assert response.status_code == 404
    with pytest.raises(ValueError, match="Budget not found"):
        await BillingService(session).update_budget(
            UUID(str(budget.id)),
            DepartmentBudgetUpdate.model_validate({"budget_limit_microcents": 200}),
            tenant_id="tenant-a",
        )
    await session.refresh(budget)
    assert budget.budget_limit_microcents == 100
