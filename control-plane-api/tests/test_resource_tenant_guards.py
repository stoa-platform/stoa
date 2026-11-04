"""Exercise resource guards through real routers, repositories and SQLite."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, MetaData, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.dependencies import User, get_current_user
from src.config import settings
from src.database import get_db
from src.models.backend_api import BackendApi
from src.models.contract import Contract, McpGeneratedTool, ProtocolBinding
from src.models.credential_mapping import CredentialMapping
from src.models.saas_api_key import SaasApiKey
from src.routers import backend_apis, contracts, credential_mappings
from src.services.cache_service import TTLCache

RESOURCES = {
    "backend-apis": BackendApi,
    "saas-keys": SaasApiKey,
    "contracts": Contract,
    "credential-mappings": CredentialMapping,
}


@pytest.fixture
async def resource_app(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    metadata = MetaData()
    for model in [*RESOURCES.values(), ProtocolBinding, McpGeneratedTool]:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ids = {}
    async with sessions() as session:
        for tenant in ["tenant-a", "tenant-b"]:
            for resource, model in RESOURCES.items():
                values = {"id": uuid4(), "tenant_id": tenant}
                if model is CredentialMapping:
                    values.update(
                        consumer_id=uuid4(),
                        api_id="fixture",
                        auth_type="api_key",
                        header_name="X-Api-Key",
                        encrypted_value="synthetic-ciphertext",
                    )
                else:
                    values["name"] = f"{tenant}-marker"
                if model is BackendApi:
                    values["backend_url"] = "https://backend.example.invalid"
                if model is SaasApiKey:
                    values.update(key_hash=f"synthetic-{tenant}", key_prefix="fixture")
                session.add(model(**values))
                ids[resource, tenant] = values["id"]
        await session.commit()

    statements = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    app = FastAPI()
    for router in [
        backend_apis.router,
        backend_apis.keys_router,
        contracts.router,
        contracts.discovery_router,
        credential_mappings.router,
    ]:
        app.include_router(router)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = database

    class RecordingCache(TTLCache):
        async def get(self, key: str):
            statements.append(f"cache:{key}")
            return await super().get(key)

    monkeypatch.setattr(contracts, "contract_cache", RecordingCache())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield app, client, ids, statements
    await engine.dispose()


def identify(app: FastAPI, role: str, tenant: str | None) -> None:
    async def current_user() -> User:
        return User(id="fixture", email="fixture@example.invalid", username="fixture", roles=[role], tenant_id=tenant)

    app.dependency_overrides[get_current_user] = current_user


@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize("role", ["cpi-admin", "tenant-admin", "devops", "viewer"])
@pytest.mark.parametrize("tenant", ["tenant-a", "tenant-b", None])
async def test_resource_reads_and_ownership(resource_app, resource, role, tenant):
    app, client, ids, statements = resource_app
    identify(app, role, tenant)
    for target in ["tenant-a", "tenant-b", " "]:
        allowed = bool(target.strip()) and (role == "cpi-admin" or target == tenant)
        path = f"/v1/tenants/{target}/{resource}"
        for suffix in ["", f"/{ids[resource, 'tenant-a']}"]:
            statements.clear()
            response = await client.get(path + suffix, headers={"X-Tenant-ID": "tenant-b"})
            if not allowed:
                assert response.status_code == 403
                assert statements == []
            elif suffix and target == "tenant-b":
                assert response.status_code == 404
            else:
                assert response.status_code == 200
                assert statements
                data = response.json()
                rows = data["items"] if not suffix else [data]
                assert len(rows) == 1
                assert all(row["tenant_id"] == target for row in rows)


@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize(
    "role,tenant",
    [
        ("tenant-admin", None),
        ("tenant-admin", "tenant-b"),
        ("viewer", "tenant-a"),
        ("devops", "tenant-a"),
        ("cpi-admin", None),
    ],
)
async def test_mutation_guards_preserve_roles(resource_app, resource, role, tenant):
    app, client, ids, statements = resource_app
    identify(app, role, tenant)
    target = " " if role == "cpi-admin" else "tenant-a"
    response = await client.delete(
        f"/v1/tenants/{target}/{resource}/{ids[resource, 'tenant-a']}", headers={"X-Tenant-ID": target}
    )
    expected = 204 if resource == "contracts" and tenant == "tenant-a" else 403
    assert response.status_code == expected
    assert bool(statements) == (expected == 204)


@pytest.mark.parametrize(
    "role,tenant,target,expected",
    [
        ("tenant-admin", "tenant-a", "tenant-a", 200),
        ("tenant-admin", "tenant-a", "tenant-b", 403),
        ("tenant-admin", None, "tenant-a", 403),
        ("cpi-admin", None, " ", 403),
        ("cpi-admin", None, "tenant-b", 200),
    ],
)
async def test_contract_discovery_scope(resource_app, role, tenant, target, expected):
    app, client, _, statements = resource_app
    identify(app, role, tenant)
    response = await client.get(
        "/v1/mcp/generated-tools", params={"tenant_id": target}, headers={"X-Tenant-ID": target}
    )
    assert response.status_code == expected
    assert bool(statements) == (expected == 200)
    if expected == 200:
        assert response.json()["tenant_id"] == target


@pytest.mark.parametrize(
    "role,target,expected", [("tenant-admin", "tenant-a", 403), ("cpi-admin", " ", 403), ("cpi-admin", "tenant-b", 200)]
)
async def test_credential_sync_guard(resource_app, role, target, expected):
    app, client, _, statements = resource_app
    identify(app, role, "tenant-a")
    response = await client.get(f"/v1/tenants/{target}/credential-mappings/sync/fixture")
    assert response.status_code == expected
    assert bool(statements) == (expected == 200)


@pytest.mark.parametrize("resource", RESOURCES)
async def test_anonymous_headers_cannot_authorize(resource_app, monkeypatch, resource):
    _, client, _, statements = resource_app
    monkeypatch.setattr(settings, "STOA_DISABLE_AUTH", False)
    response = await client.get(f"/v1/tenants/tenant-a/{resource}", headers={"X-Tenant-ID": "tenant-a"})
    assert response.status_code == 401
    assert statements == []
