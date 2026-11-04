"""Tenant claim compatibility through real signed JWTs, ASGI and tenant guards."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth import dependencies
from src.auth.dependencies import User, get_current_user
from src.auth.rbac import decide_tenant_access, require_tenant_access
from src.database import get_db
from src.models.tenant import Tenant
from src.routers.users import router


class ClaimClient(AsyncClient):
    fixture_app: FastAPI


@pytest.fixture(scope="module")
def signing_keys() -> tuple[bytes, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


def signed_headers(signing_keys: tuple[bytes, str], **claims: Any) -> dict[str, str]:
    payload = {
        "sub": "claim-user",
        "email": "claims@example.invalid",
        "preferred_username": "claims",
        "realm_access": {"roles": ["viewer"]},
        "aud": "control-plane-api",
        "iss": "https://auth.example.invalid/realms/stoa",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        **claims,
    }
    token = jwt.encode(payload, signing_keys[0], algorithm="RS256")
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": "other"}


@pytest.fixture
async def claim_client(monkeypatch: pytest.MonkeyPatch, signing_keys: tuple[bytes, str]) -> AsyncIterator[ClaimClient]:
    monkeypatch.setattr(dependencies.settings, "KEYCLOAK_URL", "https://auth.example.invalid")
    monkeypatch.setattr(dependencies.settings, "KEYCLOAK_REALM", "stoa")
    monkeypatch.setattr(dependencies.settings, "KEYCLOAK_CLIENT_ID", "control-plane-api")
    monkeypatch.setattr(dependencies.settings, "STOA_DISABLE_AUTH", False)
    monkeypatch.setattr(dependencies.settings, "LOG_DEBUG_AUTH_TOKENS", False)
    monkeypatch.setattr(dependencies.settings, "LOG_DEBUG_AUTH_PAYLOAD", False)

    async def public_key() -> str:
        return signing_keys[1]

    monkeypatch.setattr(dependencies, "get_keycloak_public_key", public_key)
    app = FastAPI()
    app.include_router(router)
    app.state.calls = []

    @app.get("/tenants/{tenant_id}")
    @require_tenant_access
    async def resource(tenant_id: str, request: Request, user: User = Depends(get_current_user)) -> dict:
        app.state.calls.append(tenant_id)
        return {"tenant_id": user.tenant_id, "state_tenant": request.state.user["tenant_id"]}

    @app.get("/global")
    async def global_read(user: User = Depends(get_current_user)) -> dict:
        return {"tenant_id": decide_tenant_access(user, mode="global")}

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Tenant.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(Tenant(id="personal", name="Personal", settings={"owner_user_id": "claim-user"}))
        await session.commit()

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = database
    async with ClaimClient(transport=ASGITransport(app=app), base_url="http://test.invalid") as client:
        client.fixture_app = app
        yield client
    await engine.dispose()


@pytest.mark.parametrize("claim", ["acme", ["acme"]])
async def test_regression_canonical_claim_ignores_client_header(
    claim_client: ClaimClient, signing_keys: tuple[bytes, str], claim: object
) -> None:
    headers = signed_headers(signing_keys, tenant_id=claim)
    response = await claim_client.get("/tenants/acme", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "acme", "state_tenant": "acme"}
    response = await claim_client.get("/tenants/other", headers=headers)
    assert response.status_code == 403
    assert claim_client.fixture_app.state.calls == ["acme"]


@pytest.mark.parametrize("role", ["viewer", "cpi-admin"])
@pytest.mark.parametrize("field", ["tenant_id", "tenant"])
@pytest.mark.parametrize(
    "claim",
    [
        None,
        "",
        " ",
        " acme",
        "acme ",
        "acme\n",
        [],
        ["acme", "other"],
        ["acme", "acme"],
        [None],
        [""],
        [" "],
        [["acme"]],
        1,
        True,
        {"id": "acme"},
        [1],
    ],
)
async def test_regression_malformed_claims_fail_authentication(
    claim_client: ClaimClient, signing_keys: tuple[bytes, str], role: str, field: str, claim: object
) -> None:
    headers = signed_headers(signing_keys, **{field: claim}, realm_access={"roles": [role]})
    response = await claim_client.get("/tenants/acme", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token: invalid_tenant_claim"}
    assert claim_client.fixture_app.state.calls == []


@pytest.mark.parametrize("claims", [{}, {"tenant": "acme"}])
@pytest.mark.parametrize("role", ["viewer", "tenant-admin", "devops", "cpi-admin", "tenant-acme"])
async def test_regression_unscoped_bootstrap_and_admin_contract(
    claim_client: ClaimClient, signing_keys: tuple[bytes, str], claims: dict, role: str
) -> None:
    headers = signed_headers(signing_keys, **claims, realm_access={"roles": [role]})
    response = await claim_client.get("/v1/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["tenant_id"] is None
    response = await claim_client.post("/v1/me/tenant", headers=headers)
    assert response.status_code == 201
    assert response.json() == {"tenant_id": "personal", "display_name": "Personal", "created": False}
    response = await claim_client.get("/global", headers=headers)
    assert response.status_code == (200 if role == "cpi-admin" else 403)
    response = await claim_client.get("/tenants/acme", headers=headers)
    assert response.status_code == (200 if role == "cpi-admin" else 403)
    assert claim_client.fixture_app.state.calls == (["acme"] if role == "cpi-admin" else [])


@pytest.mark.parametrize("role", ["viewer", "cpi-admin"])
@pytest.mark.parametrize("claims", [{"tenant_id": None}, {"tenant": None}, {"tenant_id": "acme", "tenant": None}])
async def test_regression_null_claims_deny_bootstrap_and_resource_access(
    claim_client: ClaimClient, signing_keys: tuple[bytes, str], role: str, claims: dict
) -> None:
    headers = signed_headers(signing_keys, **claims, realm_access={"roles": [role]})
    for method, path in [("GET", "/v1/me"), ("POST", "/v1/me/tenant"), ("GET", "/global"), ("GET", "/tenants/acme")]:
        response = await claim_client.request(method, path, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid token: invalid_tenant_claim"}
        assert claim_client.fixture_app.state.calls == []


@pytest.mark.parametrize("legacy", ["acme", ["acme"], "other", ["other"]])
async def test_regression_legacy_claim_must_agree(
    claim_client: ClaimClient, signing_keys: tuple[bytes, str], legacy: object
) -> None:
    response = await claim_client.get("/v1/me", headers=signed_headers(signing_keys, tenant_id="acme", tenant=legacy))
    assert response.status_code == (401 if legacy in ("other", ["other"]) else 200)
    if response.status_code == 200:
        assert response.json()["tenant_id"] == "acme"
    else:
        assert response.json() == {"detail": "Invalid token: conflicting_tenant_claims"}


async def test_regression_header_alone_cannot_authenticate(claim_client: ClaimClient) -> None:
    response = await claim_client.get("/tenants/acme", headers={"X-Tenant-ID": "acme"})
    assert response.status_code == 401
    assert claim_client.fixture_app.state.calls == []
