"""Regression tests for list access control and one-time API key delivery."""

import logging
import secrets

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config import settings
from control_plane.models.api_key import ApiKey
from control_plane.redaction import SecretRedactionFilter
from control_plane.services.api_key_service import create_api_key, hash_key


async def _headers(db: AsyncSession, role: str, tenant_id: str) -> dict[str, str]:
    _record, raw_key = await create_api_key(
        db,
        name=f"test-{role}",
        role=role,
        tenant_id=tenant_id,
    )
    return {"X-API-Key": raw_key}


class TestUnauthenticated:
    """Personal-data routes reject callers with no credentials."""

    async def test_list_invites_requires_auth(self, anon_client: AsyncClient):
        response = await anon_client.get("/api/v1/invites")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "unauthenticated"

    async def test_list_events_requires_auth(self, anon_client: AsyncClient):
        response = await anon_client.get(
            "/api/v1/events",
            params={"invite_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert response.status_code == 401

    async def test_list_api_keys_requires_auth(self, anon_client: AsyncClient):
        response = await anon_client.get("/api/v1/api-keys")
        assert response.status_code == 401


class TestRoleAndTenant:
    """Lists are limited to an allowed role and the caller's tenant."""

    async def test_devops_cannot_list_invites(
        self,
        anon_client: AsyncClient,
        db_session: AsyncSession,
    ):
        headers = await _headers(db_session, "devops", "tenant-a")
        response = await anon_client.get("/api/v1/invites", headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"

    async def test_other_tenant_cannot_read_invite(
        self,
        client: AsyncClient,
        anon_client: AsyncClient,
        db_session: AsyncSession,
    ):
        created = await client.post(
            "/api/v1/invites",
            json={"email": "owner@example.com", "company": "Owner Co"},
        )
        assert created.status_code == 201
        invite_id = created.json()["id"]
        email = created.json()["email"]

        headers = await _headers(db_session, "tenant-admin", "tenant-b")
        denied = await anon_client.get(f"/api/v1/invites/{invite_id}", headers=headers)
        assert denied.status_code == 403
        assert email not in denied.text

        listed = await anon_client.get("/api/v1/invites", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["total"] == 0
        assert email not in listed.text

        events = await anon_client.get(
            "/api/v1/events",
            params={"invite_id": invite_id},
            headers=headers,
        )
        assert events.status_code == 403
        assert email not in events.text

    async def test_viewer_can_list_own_tenant(
        self,
        client: AsyncClient,
        anon_client: AsyncClient,
        db_session: AsyncSession,
    ):
        created = await client.post(
            "/api/v1/invites",
            json={"email": "viewer-visible@example.com", "company": "Visible"},
        )
        assert created.status_code == 201

        headers = await _headers(db_session, "viewer", "tenant-a")
        response = await anon_client.get("/api/v1/invites", headers=headers)
        assert response.status_code == 200
        emails = [item["email"] for item in response.json()["invites"]]
        assert "viewer-visible@example.com" in emails

        write = await anon_client.post(
            "/api/v1/invites",
            headers=headers,
            json={"email": "nope@example.com", "company": "Nope"},
        )
        assert write.status_code == 403

    async def test_tenant_admin_can_list_own_tenant(self, client: AsyncClient):
        await client.post(
            "/api/v1/invites",
            json={"email": "admin-visible@example.com", "company": "Admin Co"},
        )
        response = await client.get("/api/v1/invites")
        assert response.status_code == 200
        emails = [item["email"] for item in response.json()["invites"]]
        assert "admin-visible@example.com" in emails


class TestApiKeyDelivery:
    """The API key is shown once, stored hashed, and kept out of logs and lists."""

    async def test_key_not_returned_after_creation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
    ):
        with caplog.at_level(logging.INFO):
            created = await client.post(
                "/api/v1/api-keys",
                json={"name": "integration", "role": "viewer"},
            )
        assert created.status_code == 201
        body = created.json()
        raw_key = body["api_key"]
        prefix = body["key_prefix"]
        assert raw_key.startswith("stoa_sk_")
        assert prefix == raw_key[: len("stoa_sk_") + 8]
        assert len(prefix) == len("stoa_sk_") + 8
        assert "key_hash" not in body

        listed = await client.get("/api/v1/api-keys")
        assert listed.status_code == 200
        assert prefix in listed.text
        assert raw_key not in listed.text
        assert "key_hash" not in listed.text
        assert all("api_key" not in item for item in listed.json()["api_keys"])

        fetched = await client.get(f"/api/v1/api-keys/{body['id']}")
        assert fetched.status_code == 200
        assert raw_key not in fetched.text
        assert "api_key" not in fetched.json()
        assert "key_hash" not in fetched.json()

        stored = await db_session.execute(select(ApiKey).where(ApiKey.id == body["id"]))
        record = stored.scalar_one()
        assert record.key_hash == hash_key(raw_key)
        assert raw_key not in record.key_hash
        assert "api key created" in caplog.text
        assert raw_key not in caplog.text

    async def test_invite_token_absent_from_lists(self, client: AsyncClient):
        created = await client.post(
            "/api/v1/invites",
            json={"email": "once@example.com", "company": "Once"},
        )
        token = created.json()["token"]
        invite_id = created.json()["id"]

        listed = await client.get("/api/v1/invites")
        assert token not in listed.text
        fetched = await client.get(f"/api/v1/invites/{invite_id}")
        assert token not in fetched.text
        assert "token" not in fetched.json()

    async def test_welcome_does_not_store_token(
        self,
        client: AsyncClient,
    ):
        created = await client.post(
            "/api/v1/invites",
            json={"email": "welcome@example.com", "company": "Welcome"},
        )
        token = created.json()["token"]
        invite_id = created.json()["id"]
        await client.get(f"/welcome/{token}", follow_redirects=False)

        events = await client.get("/api/v1/events", params={"invite_id": invite_id})
        assert events.status_code == 200
        assert token not in events.text

    async def test_log_filter_redacts_api_key(self):
        raw_key = "stoa_sk_" + secrets.token_hex(16)
        record = logging.LogRecord(
            name="control_plane",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="issued %s",
            args=(raw_key,),
            exc_info=None,
        )
        assert SecretRedactionFilter().filter(record) is True
        assert raw_key not in record.getMessage()
        assert "stoa_sk_[redacted]" in record.getMessage()


class TestMigrationDowngrade:
    """Hashed invite tokens cannot be turned back into working links."""

    def test_downgrade_is_refused(self):
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "003_api_keys_and_tenant_scope.py"
        )
        spec = importlib.util.spec_from_file_location("migration_003", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with pytest.raises(RuntimeError, match="cannot be downgraded"):
            module.downgrade()


class TestBootstrapAdmin:
    """Bootstrap auth compares a configured digest and does not store the key."""

    async def test_bootstrap_hash_can_list(
        self,
        anon_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        raw_key = "stoa_sk_" + secrets.token_hex(16)
        monkeypatch.setattr(settings, "bootstrap_admin_key_hash", hash_key(raw_key))
        monkeypatch.setattr(settings, "bootstrap_admin_tenant", "platform")

        response = await anon_client.get(
            "/api/v1/invites",
            headers={"X-API-Key": raw_key},
        )
        assert response.status_code == 200
        monkeypatch.setattr(settings, "bootstrap_admin_key_hash", "")
