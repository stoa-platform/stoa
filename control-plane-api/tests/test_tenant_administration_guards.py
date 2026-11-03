"""Exercise tenant administration through ASGI and real SQLite repositories."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from src.auth.dependencies import User, get_current_user
from src.database import Base, get_db
from src.routers import tenants
from src.services import tenant_dr_service as dr
from src.services.cache_service import TTLCache
from src.services.git_provider import get_git_provider

ROOT = "/v1/tenants"
ARCHIVE = {"metadata": {"tenant_id": "tenant-b", "exported_at": "2026-01-01T00:00:00Z"}}
CREATE = {"name": "new", "display_name": "New", "owner_email": "owner@example.invalid"}
READS = [("GET", suffix, None) for suffix in ("", "/usage", "/provisioning-status", "/export")]
WRITES = [("POST", "/import", {"archive": ARCHIVE}), ("PUT", "", {}), ("DELETE", "", None)]
Operation = tuple[str, str, dict | None]


@compiles(JSONB, "sqlite")
def compile_jsonb(element: object, compiler: object, **kwargs: object) -> str:
    return "JSON"


def identity(role: str = "tenant-admin", tenant: str | None = "tenant-a") -> User:
    return User(id="synthetic", email="user@example.invalid", username="synthetic", roles=[role], tenant_id=tenant)


@pytest.fixture
async def access(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    models = (
        dr.Tenant,
        dr.BackendApi,
        dr.Contract,
        dr.ProtocolBinding,
        dr.Consumer,
        dr.Plan,
        dr.Subscription,
        dr.GatewayPolicy,
        dr.Skill,
        dr.TenantWebhook,
        dr.ExternalMCPServer,
        dr.ExternalMCPServerTool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models]))
    async with sessions() as session:
        for tenant in ("tenant-a", "tenant-b"):
            session.add(dr.Tenant(id=tenant, name=tenant, settings={"max_apis": 7, "max_applications": 9}))
            session.add(dr.BackendApi(tenant_id=tenant, name=f"{tenant}-api", backend_url="https://example.invalid"))
        await session.commit()
    state = SimpleNamespace(user=identity(), sql=[], effects=[])

    def observe_sql(*args: object) -> None:
        state.sql.append(args[2])

    event.listen(engine.sync_engine, "before_cursor_execute", observe_sql)

    async def external(*args: object, **kwargs: object) -> list[object]:
        state.effects.append((args, kwargs))
        return []

    class ObservedCache(TTLCache):
        async def get(self, key: str) -> object:
            state.effects.append(("cache", key))
            return await super().get(key)

    monkeypatch.setattr(tenants, "tenant_cache", ObservedCache())
    monkeypatch.setattr(tenants, "keycloak_service", SimpleNamespace(get_clients=external, create_realm=external))
    monkeypatch.setattr(tenants, "kafka_service", SimpleNamespace(publish=external, emit_audit_event=external))
    monkeypatch.setattr(tenants, "provision_tenant", external)
    monkeypatch.setattr(tenants, "deprovision_tenant", external)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session
            await session.commit()

    app = FastAPI()
    app.include_router(tenants.router)
    app.dependency_overrides[get_current_user] = lambda: state.user
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_git_provider] = lambda: SimpleNamespace(list_apis=external)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state.client = client
        state.app = app
        yield state
    await engine.dispose()


@pytest.mark.parametrize("operation", READS + WRITES)
@pytest.mark.parametrize("tenant", ["tenant-b", None, "", "   "])
@pytest.mark.parametrize("role", ["tenant-admin", "devops", "viewer"])
async def test_denial_precedes_database_cache_and_external_calls(
    access: SimpleNamespace, operation: Operation, tenant: str | None, role: str
) -> None:
    access.user = identity(role, tenant)
    method, suffix, body = operation
    response = await access.client.request(
        method, f"{ROOT}/tenant-a{suffix}", json=body, headers={"X-Tenant-ID": "tenant-a"}
    )
    assert response.status_code == 403
    assert access.sql == access.effects == []


@pytest.mark.parametrize("role", ["tenant-admin", "devops", "viewer"])
@pytest.mark.parametrize("tenant", [None, "", "   "])
async def test_list_requires_authenticated_tenant(access: SimpleNamespace, role: str, tenant: str | None) -> None:
    access.user = identity(role, tenant)
    response = await access.client.get(ROOT, headers={"X-Tenant-ID": "tenant-a"})
    assert response.status_code == 403
    assert access.sql == access.effects == []


@pytest.mark.parametrize("operation", READS + WRITES)
async def test_admin_requires_nonblank_target(access: SimpleNamespace, operation: Operation) -> None:
    access.user = identity("cpi-admin", None)
    method, suffix, body = operation
    response = await access.client.request(method, f"{ROOT}/%20{suffix}", json=body)
    assert response.status_code == 403
    assert access.sql == access.effects == []


@pytest.mark.parametrize("role", ["tenant-admin", "devops", "viewer"])
@pytest.mark.parametrize("tenant", ["tenant-a", "tenant-b"])
async def test_reads_are_scoped_to_signed_identity(access: SimpleNamespace, role: str, tenant: str) -> None:
    access.user = identity(role, tenant)
    other = "tenant-b" if tenant == "tenant-a" else "tenant-a"
    response = await access.client.get(ROOT, headers={"X-Tenant-ID": other})
    assert [item["id"] for item in response.json()] == [tenant]
    for _, suffix, _ in READS:
        response = await access.client.get(f"{ROOT}/{tenant}{suffix}", headers={"X-Tenant-ID": other})
        assert response.status_code == 200
        assert other not in response.text
        if suffix == "/usage":
            assert response.json()["max_apis"] == 7
            assert response.json()["max_applications"] == 9
        if suffix == "/export":
            assert [api["name"] for api in response.json()["backend_apis"]] == [f"{tenant}-api"]
        denied = await access.client.get(f"{ROOT}/{other}{suffix}", headers={"X-Tenant-ID": other})
        assert denied.status_code == 403
        assert other not in denied.text


@pytest.mark.parametrize("role", ["tenant-admin", "devops", "viewer"])
@pytest.mark.parametrize("operation", [*WRITES, ("POST", "/create", CREATE), ("POST", "/provision", CREATE)])
async def test_existing_write_permissions_are_preserved(
    access: SimpleNamespace, role: str, operation: Operation
) -> None:
    access.user = identity(role)
    method, suffix, body = operation
    path = ROOT if suffix == "/create" else f"{ROOT}{suffix}" if suffix == "/provision" else f"{ROOT}/tenant-a{suffix}"
    response = await access.client.request(method, path, json=body)
    assert response.status_code == 403
    assert access.sql == access.effects == []


@pytest.mark.parametrize("suffix", ["", "/provision"])
async def test_admin_creation_requires_target(access: SimpleNamespace, suffix: str) -> None:
    access.user = identity("cpi-admin", None)
    response = await access.client.post(f"{ROOT}{suffix}", json={**CREATE, "name": ""})
    assert response.status_code == 403
    assert access.sql == access.effects == []


async def test_admin_explicit_targets_and_portable_import(access: SimpleNamespace) -> None:
    access.user = identity("cpi-admin", None)
    response = await access.client.get(ROOT)
    assert {item["id"] for item in response.json()} == {"tenant-a", "tenant-b"}
    for tenant in ("tenant-a", "tenant-b"):
        for _, suffix, _ in READS:
            assert (await access.client.get(f"{ROOT}/{tenant}{suffix}")).status_code == 200
    archive = {
        **ARCHIVE,
        "backend_apis": [{"id": str(uuid4()), "name": "imported", "backend_url": "https://example.invalid"}],
    }
    response = await access.client.post(f"{ROOT}/tenant-a/import", json={"archive": archive})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-a"
    assert response.json()["created"] == {"backend_apis": 1}
    for tenant, expected in (("tenant-a", ["tenant-a-api", "imported"]), ("tenant-b", ["tenant-b-api"])):
        exported = await access.client.get(f"{ROOT}/{tenant}/export")
        assert sorted(api["name"] for api in exported.json()["backend_apis"]) == sorted(expected)
    response = await access.client.put(f"{ROOT}/tenant-a", json={"display_name": "Changed"})
    assert response.status_code == 200
    assert response.json()["name"] == "Changed"
    assert (await access.client.get(f"{ROOT}/tenant-b")).json()["name"] == "tenant-b"
    assert (await access.client.post(ROOT, json=CREATE)).status_code == 200
    assert (await access.client.post(f"{ROOT}/provision", json={**CREATE, "name": "provisioned"})).status_code == 201
    assert (await access.client.delete(f"{ROOT}/tenant-a")).status_code == 200


async def test_cached_tenant_cannot_cross_identity_boundary(access: SimpleNamespace) -> None:
    assert (await access.client.get(f"{ROOT}/tenant-a")).status_code == 200
    access.user = identity(tenant="tenant-b")
    access.sql.clear()
    access.effects.clear()
    response = await access.client.get(f"{ROOT}/tenant-a", headers={"X-Tenant-ID": "tenant-a"})
    assert response.status_code == 403
    assert access.sql == access.effects == []


async def test_anonymous_requests_are_refused(access: SimpleNamespace) -> None:
    access.app.dependency_overrides.pop(get_current_user)
    for method, suffix, body in READS + WRITES:
        response = await access.client.request(method, f"{ROOT}/tenant-a{suffix}", json=body)
        assert response.status_code == 401
    for suffix in ("", "/provision"):
        response = await access.client.post(f"{ROOT}{suffix}", json=CREATE)
        assert response.status_code == 401
    assert (await access.client.get(ROOT)).status_code == 401
    assert access.sql == access.effects == []
