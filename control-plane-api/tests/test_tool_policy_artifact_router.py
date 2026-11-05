"""HTTP policy issuance through real SQL, snapshot assembly and Ed25519 signing."""

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth import User, get_current_user
from src.config import settings
from src.database import get_db
from src.models.tenant_tool_permission import TenantToolPermission
from src.models.tool_policy_version import ToolPolicyVersion
from src.routers import tenant_tool_permissions as routes
from src.services import tool_policy_snapshot as snapshots
from tests import test_tool_policy_snapshot as fixtures
from tests.test_tool_policy_snapshot import SERVER_A, TENANT, decode, row, seed

db = fixtures.db
signing_key = fixtures.signing_key

URL = f"/v1/tenants/{TENANT}/tool-permissions"
NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


class Clock(datetime):
    current = NOW

    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return cls.current


@pytest.fixture
async def client(db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(routes.router)
    monkeypatch.setattr(routes, "datetime", Clock)
    monkeypatch.setattr(snapshots, "datetime", Clock)
    Clock.current = NOW
    await routes._artifact_cache.clear()

    async def session() -> AsyncIterator[AsyncSession]:
        async with db() as connection:
            yield connection

    app.dependency_overrides[get_db] = session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        http.test_app = app
        yield http
    await routes._artifact_cache.clear()


def authenticate(client: AsyncClient, role: str = "tenant-admin", tenant: str | None = TENANT) -> None:
    client.test_app.dependency_overrides[get_current_user] = lambda: User(
        id="reader", email="reader@example.test", username="reader", roles=[role], tenant_id=tenant
    )


def verified(response: Response, key: Ed25519PrivateKey) -> dict:
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/jose"
    assert response.headers["etag"] == f'"{hashlib.sha256(response.content).hexdigest()}"'
    header, payload, signature = response.text.split(".")
    key.public_key().verify(decode(signature), f"{header}.{payload}".encode("ascii"))
    assert json.loads(decode(header))["typ"] == "stoa-tool-policy+jws"
    return json.loads(decode(payload))


@pytest.mark.parametrize("role", ["cpi-admin", "tenant-admin", "devops", "viewer"])
async def test_signed_complete_policy_and_admin_listing(
    client: AsyncClient, db: async_sessionmaker[AsyncSession], signing_key: Ed25519PrivateKey, role: str
) -> None:
    authenticate(client, role)
    rows = [row(TENANT, SERVER_A, f"tool-{i:03d}", i % 2 == 0) for i in range(120)]
    await seed(db, [*rows, row("other", SERVER_A, "private")], {TENANT: 7, "other": 8})
    response = await client.get(URL + "/artifact", params={"page_size": 1, "issued_at": "2099-01-01"})
    policy = verified(response, signing_key)
    assert policy["tenant_id"] == TENANT and policy["version"] == 7
    assert len(policy["permissions"]) == 120
    assert sum(p["allowed"] for p in policy["permissions"]) == 60
    assert datetime.fromisoformat(policy["issued_at"]) == NOW
    assert datetime.fromisoformat(policy["expires_at"]) == NOW + timedelta(seconds=900)
    assert response.headers["cache-control"] == "private, no-cache"
    listing = await client.get(URL, params={"page_size": 100})
    assert listing.status_code == 200
    assert listing.json()["total"] == 120 and len(listing.json()["items"]) == 100


async def test_authentication_and_tenant_isolation_even_with_etag(
    client: AsyncClient, db: async_sessionmaker[AsyncSession], signing_key: Ed25519PrivateKey
) -> None:
    await seed(db, [row(TENANT, SERVER_A, "read")], {TENANT: 2})
    assert (await client.get(URL + "/artifact")).status_code in (401, 403)
    authenticate(client)
    response = await client.get(URL + "/artifact")
    verified(response, signing_key)
    authenticate(client, tenant="other")
    denied = await client.get(URL + "/artifact", headers={"If-None-Match": response.headers["etag"]})
    assert denied.status_code == 403 and "etag" not in denied.headers
    authenticate(client, "viewer", None)
    assert (await client.get(URL + "/artifact")).status_code == 403
    authenticate(client, "cpi-admin", None)
    assert (await client.get(URL + "/artifact")).status_code == 200
    missing = await client.get("/v1/tenants/missing/tool-permissions/artifact")
    assert missing.status_code == 404


async def test_conditional_get_mutation_reissue_and_expiry(
    client: AsyncClient, db: async_sessionmaker[AsyncSession], signing_key: Ed25519PrivateKey
) -> None:
    authenticate(client)
    await seed(db, [], {TENANT: 2})
    first = await client.get(URL + "/artifact")
    verified(first, signing_key)
    Clock.current += timedelta(seconds=10)
    same = await client.get(URL + "/artifact")
    assert same.content == first.content and same.headers["etag"] == first.headers["etag"]
    for match in [first.headers["etag"], f'"unrelated", W/{first.headers["etag"]}', "*"]:
        unchanged = await client.get(URL + "/artifact", headers={"If-None-Match": match})
        assert unchanged.status_code == 304 and unchanged.content == b""
        assert unchanged.headers["cache-control"] == "private, no-cache"
    async with db.begin() as session:
        await session.execute(insert(TenantToolPermission), [row(TENANT, SERVER_A, "new")])
        await session.execute(update(ToolPolicyVersion).values(version=3))
    changed = await client.get(URL + "/artifact", headers={"If-None-Match": first.headers["etag"]})
    assert verified(changed, signing_key)["version"] == 3
    assert changed.headers["etag"] != first.headers["etag"]
    Clock.current += timedelta(seconds=10)
    renewed = await client.get(URL + "/artifact?reissue=true", headers={"If-None-Match": changed.headers["etag"]})
    assert verified(renewed, signing_key)["issued_at"] != verified(changed, signing_key)["issued_at"]
    Clock.current += timedelta(seconds=900)
    expired = await client.get(URL + "/artifact", headers={"If-None-Match": renewed.headers["etag"]})
    assert verified(expired, signing_key)["issued_at"] != verified(renewed, signing_key)["issued_at"]


@pytest.mark.parametrize("failure", ["signer", "cap", "validation"])
async def test_failures_never_return_artifact_or_304(
    client: AsyncClient,
    db: async_sessionmaker[AsyncSession],
    signing_key: Ed25519PrivateKey,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    authenticate(client)
    await seed(db, [], {TENANT: 2})
    previous = await client.get(URL + "/artifact")
    verified(previous, signing_key)
    if failure == "signer":
        monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KEY_FILE", "/synthetic-sensitive-path/not-present")
    else:
        if failure == "cap":
            monkeypatch.setattr(snapshots, "MAX_POLICY_ENTRIES", 0)
        async with db.begin() as session:
            await session.execute(
                insert(TenantToolPermission), [row(TENANT, SERVER_A, "" if failure == "validation" else "x")]
            )
    response = await client.get(URL + "/artifact", headers={"If-None-Match": previous.headers["etag"]})
    assert response.status_code == (413 if failure == "cap" else 503)
    assert "etag" not in response.headers
    assert "artifact" not in response.json()
    assert "synthetic-sensitive-path" not in response.text + caplog.text
