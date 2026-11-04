"""Exercise real tenant authorization, federation repositories, and CA SQL with SQLite."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from src.auth.dependencies import User, get_current_user
from src.database import Base, get_db
from src.models.federation import MasterAccount, SubAccount, SubAccountTool
from src.models.signed_certificate import SignedCertificate
from src.models.tenant import Tenant
from src.models.tenant_ca import TenantCA
from src.routers import federation, tenant_ca

MID = [uuid4(), uuid4()]
SID = [uuid4(), uuid4()]
CID = [uuid4(), uuid4()]
FED = "/v1/tenants/tenant-a/federation/accounts"
CA = "/v1/tenants/tenant-a/ca"
MASTER = f"{FED}/{MID[0]}"
SUB = f"{MASTER}/sub-accounts/{SID[0]}"
OPS = [
    ("POST", FED, {"name": "new"}),
    ("GET", FED, None),
    ("GET", MASTER, None),
    ("PATCH", MASTER, {"display_name": "changed"}),
    ("DELETE", MASTER, None),
    ("POST", f"{MASTER}/sub-accounts", {"name": "new"}),
    ("GET", f"{MASTER}/sub-accounts", None),
    ("GET", SUB, None),
    ("PATCH", SUB, {"display_name": "changed"}),
    ("POST", f"{SUB}/revoke", None),
    ("POST", f"{MASTER}/delegate-token", {}),
    ("GET", f"{MASTER}/usage", None),
    ("POST", f"{MASTER}/bulk-revoke", None),
    ("PUT", f"{SUB}/tools", {"tools": []}),
    ("GET", f"{SUB}/tools", None),
    ("POST", f"{CA}/generate", None),
    ("GET", CA, None),
    ("POST", f"{CA}/sign", {"csr_pem": "synthetic"}),
    ("DELETE", CA, None),
    ("GET", f"{CA}/certificates", None),
    ("POST", f"{CA}/certificates/{CID[0]}/revoke", None),
]


@compiles(JSONB, "sqlite")
def compile_jsonb(element: object, compiler: object, **kwargs: object) -> str:
    return "JSON"


def user(role: str = "tenant-admin", tenant: str | None = "tenant-a") -> User:
    return User(id="synthetic", email="synthetic@example.invalid", username="synthetic", roles=[role], tenant_id=tenant)


@pytest.fixture
async def access(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tables = [
        model.__table__ for model in (Tenant, TenantCA, SignedCertificate, MasterAccount, SubAccount, SubAccountTool)
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    now = datetime.now(UTC)
    async with sessions() as session:
        for index, tenant in enumerate(("tenant-a", "tenant-b")):
            session.add(Tenant(id=tenant, name=tenant))
            ca = TenantCA(
                id=uuid4(),
                tenant_id=tenant,
                ca_certificate_pem="public-fixture",
                encrypted_private_key="",
                subject_dn=tenant,
                serial_number=tenant,
                not_before=now,
                not_after=now,
                fingerprint_sha256=tenant,
            )
            session.add(ca)
            session.add(MasterAccount(id=MID[index], tenant_id=tenant, name=tenant))
            session.add(SubAccount(id=SID[index], master_account_id=MID[index], tenant_id=tenant, name=tenant))
            session.add(
                SignedCertificate(
                    id=CID[index],
                    tenant_id=tenant,
                    ca_id=ca.id,
                    subject_dn=tenant,
                    issuer_dn=tenant,
                    serial_number=tenant,
                    not_before=now,
                    not_after=now,
                    fingerprint_sha256=tenant,
                    certificate_pem="public",
                )
            )
        await session.commit()
    state = SimpleNamespace(user=user(), sql=[], service_calls=0)

    def observe_sql(*args: object) -> None:
        state.sql.append(args[2])

    event.listen(engine.sync_engine, "before_cursor_execute", observe_sql)
    original_service = federation.FederationService

    class ObservedService(original_service):
        def __init__(self, session):
            state.service_calls += 1
            super().__init__(session)

    monkeypatch.setattr(federation, "FederationService", ObservedService)

    async def database():
        async with sessions() as session:
            yield session
            await session.commit()

    app = FastAPI()
    app.include_router(federation.router)
    app.include_router(tenant_ca.router)
    app.dependency_overrides[get_current_user] = lambda: state.user
    app.dependency_overrides[get_db] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state.client = client
        yield state
    await engine.dispose()


@pytest.mark.parametrize("operation", OPS)
@pytest.mark.parametrize("tenant", ["tenant-b", None, "", "   "])
async def test_regression_tenant_denial_precedes_all_service_and_database_calls(access, operation, tenant):
    access.user = user(tenant=tenant)
    method, path, body = operation
    response = await access.client.request(method, path, json=body, headers={"X-Tenant-ID": "tenant-a"})
    assert response.status_code == 403
    assert access.sql == []
    assert access.service_calls == 0


@pytest.mark.parametrize("operation", OPS)
async def test_regression_admin_requires_nonblank_explicit_target(access, operation):
    access.user = user("cpi-admin", None)
    method, path, body = operation
    response = await access.client.request(method, path.replace("tenant-a", "%20"), json=body)
    assert response.status_code == 403
    assert access.sql == []
    assert access.service_calls == 0


@pytest.mark.parametrize("role", ["cpi-admin", "tenant-admin", "devops", "viewer"])
async def test_regression_existing_roles_preserve_read_write_and_platform_only_access(access, role):
    access.user = user(role, None if role == "cpi-admin" else "tenant-a")
    for path in (FED, CA):
        assert (await access.client.get(path)).status_code == 200
    can_write = role in ("cpi-admin", "tenant-admin")
    response = await access.client.post(FED, json={"name": "created"})
    assert response.status_code == (201 if can_write else 403)
    response = await access.client.post(f"{CA}/certificates/{CID[0]}/revoke")
    assert response.status_code == (200 if can_write else 403)
    for path in (MASTER, CA):
        response = await access.client.delete(path)
        expected = (204 if path == MASTER else 200) if role == "cpi-admin" else 403
        assert response.status_code == expected


@pytest.mark.parametrize("index", [0, 1])
async def test_regression_database_lists_and_objects_are_isolated_between_tenants(access, index):
    own, foreign = index, 1 - index
    tenant = ("tenant-a", "tenant-b")[own]
    access.user = user(tenant=tenant)
    fed, ca = FED.replace("tenant-a", tenant), CA.replace("tenant-a", tenant)
    response = await access.client.get(fed)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(MID[own])]
    response = await access.client.get(f"{fed}/{MID[own]}/sub-accounts")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(SID[own])]
    response = await access.client.get(f"{ca}/certificates")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(CID[own])]
    assert (await access.client.get(f"{fed}/{MID[own]}")).status_code == 200
    assert (await access.client.get(ca)).json()["tenant_id"] == tenant
    paths = [
        f"{fed}/{MID[foreign]}",
        f"{fed}/{MID[foreign]}/sub-accounts",
        f"{fed}/{MID[own]}/sub-accounts/{SID[foreign]}",
    ]
    for path in paths:
        assert (await access.client.get(path)).status_code == 404
    response = await access.client.patch(paths[0], json={"display_name": "changed"})
    assert response.status_code == 404
    response = await access.client.post(f"{paths[2]}/revoke")
    assert response.status_code == 404
    response = await access.client.post(f"{ca}/certificates/{CID[foreign]}/revoke")
    assert response.status_code == 404
    access.user = user(tenant=("tenant-a", "tenant-b")[foreign])
    foreign_fed = FED.replace("tenant-a", access.user.tenant_id)
    response = await access.client.get(f"{foreign_fed}/{MID[foreign]}/sub-accounts/{SID[foreign]}")
    assert response.json()["status"] == "active"
    foreign_ca = CA.replace("tenant-a", access.user.tenant_id)
    response = await access.client.get(f"{foreign_ca}/certificates")
    assert response.json()["items"][0]["status"] == "active"
