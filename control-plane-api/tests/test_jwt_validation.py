"""Tests for JWT validation in get_current_user (CAB-1292 Phase 2)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User, get_current_user


def _make_app():
    app = FastAPI()

    @app.get("/me")
    async def me(user: User = pytest.importorskip("fastapi").Depends(get_current_user)):
        return {"id": user.id, "email": user.email, "tenant_id": user.tenant_id, "roles": user.roles}

    return app


def _base_payload(**overrides):
    base = {
        "sub": "user-123",
        "email": "user@acme.com",
        "preferred_username": "testuser",
        "realm_access": {"roles": ["viewer"]},
        "tenant_id": "acme",
        "aud": ["control-plane-api"],
        "azp": "control-plane-ui",
        "iss": "https://auth.gostoa.dev/realms/stoa",
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_settings():
    with patch("src.auth.dependencies.settings") as m:
        m.KEYCLOAK_URL = "https://auth.gostoa.dev"
        m.keycloak_internal_url = "https://auth.gostoa.dev"
        m.KEYCLOAK_REALM = "stoa"
        m.KEYCLOAK_CLIENT_ID = "control-plane-api"
        m.gateway_api_keys_list = []
        m.LOG_DEBUG_AUTH_TOKENS = False
        m.LOG_DEBUG_AUTH_PAYLOAD = False
        yield m


@pytest.fixture
def mock_kc_key():
    with patch("src.auth.dependencies.get_keycloak_public_key", new_callable=AsyncMock) as m:
        m.return_value = "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----"
        yield m


class TestJwtValidation:

    @pytest.mark.asyncio
    async def test_valid_token(self, mock_settings, mock_kc_key):
        payload = _base_payload()
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer valid-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "user-123"
        assert data["email"] == "user@acme.com"
        assert data["tenant_id"] == "acme"

    @pytest.mark.asyncio
    async def test_invalid_audience_401(self, mock_settings, mock_kc_key):
        payload = _base_payload(aud=["some-other-api"])
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer bad-aud"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_sub_email_fallback(self, mock_settings, mock_kc_key):
        payload = _base_payload(sub=None, email="fallback@acme.com")
        del payload["sub"]
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer no-sub"})
        assert resp.status_code == 200
        assert resp.json()["id"] == "fallback@acme.com"

    @pytest.mark.asyncio
    async def test_missing_sub_no_email_401(self, mock_settings, mock_kc_key):
        payload = _base_payload()
        del payload["sub"]
        payload["email"] = ""
        payload["preferred_username"] = ""
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer no-id"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_tenant_id_as_list(self, mock_settings, mock_kc_key):
        payload = _base_payload(tenant_id=["acme", "globex"])
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer list-tenant"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "acme"

    @pytest.mark.asyncio
    async def test_legacy_audience_accepted(self, mock_settings, mock_kc_key):
        payload = _base_payload(aud=["control-plane-ui"])
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer legacy-aud"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_aud_as_string(self, mock_settings, mock_kc_key):
        payload = _base_payload(aud="control-plane-api")
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer str-aud"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_jwt_decode_error_401(self, mock_settings, mock_kc_key):
        from jose import JWTError

        with patch("src.auth.dependencies.jwt.decode", side_effect=JWTError("bad token")):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer bad-jwt"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_sub_uuid_used_as_user_id(self, mock_settings, mock_kc_key):
        """CAB-1669: When 'sub' claim is a Keycloak UUID, user.id must use it."""
        keycloak_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        payload = _base_payload(sub=keycloak_uuid)
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer uuid-sub"})
        assert resp.status_code == 200
        assert resp.json()["id"] == keycloak_uuid

    @pytest.mark.asyncio
    async def test_sub_preferred_over_email(self, mock_settings, mock_kc_key):
        """CAB-1669: 'sub' claim must take precedence over email for user.id."""
        payload = _base_payload(sub="keycloak-uuid-123", email="user@acme.com")
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer sub-pref"})
        assert resp.status_code == 200
        # user.id must be the sub claim, not the email
        assert resp.json()["id"] == "keycloak-uuid-123"
        assert resp.json()["email"] == "user@acme.com"

    @pytest.mark.asyncio
    async def test_missing_sub_falls_back_to_username(self, mock_settings, mock_kc_key):
        """CAB-1669: When sub is missing and email is empty, fall back to username."""
        payload = _base_payload()
        del payload["sub"]
        payload["email"] = ""
        payload["preferred_username"] = "admin-user"
        with patch("src.auth.dependencies.jwt.decode", return_value=payload):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer no-sub-no-email"})
        assert resp.status_code == 200
        assert resp.json()["id"] == "admin-user"

    @pytest.mark.asyncio
    async def test_keycloak_unreachable_503(self, mock_settings):
        import httpx

        with patch(
            "src.auth.dependencies.get_keycloak_public_key",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer any"})
        assert resp.status_code == 503
