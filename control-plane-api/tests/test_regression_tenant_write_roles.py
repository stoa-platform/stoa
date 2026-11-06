"""Regression coverage for tenant write roles and budget update scoping."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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


WRITE_ROLES = ["tenant-admin", "cpi-admin", "devops", "stoa.product_owner", "stoa.admin", "stoa.developer"]
READ_ROLES = ["viewer", "stoa.consumer", "stoa.security", "stoa.agent", "unknown"]
CONSUMER_WRITES = ["bulk", "suspend", "activate", "block", "bind", "revoke", "rotate", "bulk-revoke"]


@pytest.fixture(scope="module")
def certificate_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "consumer.example.test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


async def consumer_write(client: AsyncClient, operation: str, tenant: str, cid: str, pem: str):
    base = f"/v1/consumers/{tenant}"
    if operation == "bulk":
        return await client.post(
            f"{base}/bulk",
            files={
                "file": ("consumers.csv", "external_id,name,email\nsecond,Second,second@example.test\n", "text/csv")
            },
        )
    if operation == "bulk-revoke":
        return await client.post(f"{base}/certificates/bulk-revoke", json={"consumer_ids": [cid]})
    suffix = {"bind": "certificate", "revoke": "certificate/revoke", "rotate": "certificate/rotate"}
    return await client.post(
        f"{base}/{cid}/{suffix.get(operation, operation)}",
        json={"certificate_pem": pem} if operation in ("bind", "rotate") else {},
    )


@pytest.mark.parametrize("operation", CONSUMER_WRITES)
@pytest.mark.parametrize("role", WRITE_ROLES + READ_ROLES)
@pytest.mark.parametrize("scope", ["own", "foreign-resource", "foreign-tenant"])
async def test_regression_cab_2441_consumer_write_routes(
    api: FastAPI,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    certificate_pem: str,
    operation: str,
    role: str,
    scope: str,
) -> None:
    if scope == "foreign-resource" and operation == "bulk":
        pytest.skip("CSV creation has no existing resource")
    external = MagicMock()
    for method in (
        "create_consumer_client",
        "create_consumer_client_with_cert",
        "update_consumer_client_cnf",
        "disable_consumer_client",
    ):
        setattr(external, method, AsyncMock(return_value={"client_id": "test", "client_secret": "test"}))
    monkeypatch.setattr(consumers, "keycloak_service", external)
    consumer = Consumer(
        tenant_id="tenant-b" if scope == "foreign-resource" else "tenant-a",
        external_id="first",
        name="First",
        email="first@example.test",
        status="suspended" if operation == "activate" else "active",
        certificate_fingerprint=None if operation == "bind" else "a" * 64,
        certificate_status="active",
    )
    session.add(consumer)
    await session.commit()
    before = {column.name: getattr(consumer, column.name) for column in Consumer.__table__.columns}
    set_user(api, role)
    tenant = "tenant-b" if scope == "foreign-tenant" else "tenant-a"
    allowed = role in WRITE_ROLES
    admin = role in ("cpi-admin", "stoa.admin")
    denied = not allowed or (scope == "foreign-tenant" and not admin)
    mismatch = scope == "foreign-resource" or (scope == "foreign-tenant" and operation != "bulk")
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await consumer_write(client, operation, tenant, str(consumer.id), certificate_pem)
        if denied:
            assert response.status_code == 403, response.text
        elif mismatch:
            if operation == "bulk-revoke":
                assert response.status_code == 200, response.text
                assert response.json()["failed"] == 1
                assert response.json()["success"] == 0
            else:
                assert response.status_code == 404, response.text
        else:
            assert response.status_code == (201 if operation == "bind" else 200), response.text
            if operation in ("bulk", "bulk-revoke"):
                assert response.json()["success"] == 1
        await session.refresh(consumer)
        rows = list((await session.execute(select(Consumer))).scalars())
        if denied or mismatch:
            assert len(rows) == 1
            assert {column.name: getattr(consumer, column.name) for column in Consumer.__table__.columns} == before
            assert external.mock_calls == []
        elif operation == "bulk":
            assert len(rows) == 2
            assert rows[1].tenant_id == tenant
            external.create_consumer_client.assert_awaited_once()
        elif operation in ("suspend", "activate", "block"):
            assert consumer.status == {"suspend": "suspended", "activate": "active", "block": "blocked"}[operation]
            if operation == "activate":
                external.create_consumer_client.assert_awaited_once()
        else:
            assert consumer.certificate_status == (
                "active" if operation == "bind" else "rotating" if operation == "rotate" else "revoked"
            )
            if operation in ("bind", "rotate"):
                assert consumer.certificate_fingerprint != before["certificate_fingerprint"]
        if scope == "own":
            persisted = {column.name: getattr(consumer, column.name) for column in Consumer.__table__.columns}
            for path in (
                f"/v1/consumers/tenant-a/{consumer.id}",
                "/v1/consumers/tenant-a",
                "/v1/consumers/tenant-a/certificates/expiring?days=1",
            ):
                assert (await client.get(path)).status_code == 200
            await session.refresh(consumer)
            assert {column.name: getattr(consumer, column.name) for column in Consumer.__table__.columns} == persisted
