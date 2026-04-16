"""Regression tests for CAB-2082 (Security P0-01).

Before the fix:
- `jwt.decode` was called with `verify_iss` disabled — any token whose signing
  key matched (e.g. leaked/rotated public key from another Keycloak realm or a
  MITM-injected public key) would be accepted.
- The Keycloak realm public key was refetched over HTTP on every request, with
  no timeout and no cache — a slow Keycloak turned into API-wide latency.

After the fix:
- `jwt.decode` enforces `issuer=<keycloak_url>/realms/<realm>`.
- The public key is cached in-memory for 5 minutes; the httpx call has a 3 s
  timeout.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import JWTError

from src.auth.dependencies import (
    User,
    _clear_keycloak_public_key_cache,
    get_current_user,
    get_keycloak_public_key,
)


def _make_app():
    app = FastAPI()

    @app.get("/me")
    async def me(user: User = pytest.importorskip("fastapi").Depends(get_current_user)):
        return {"id": user.id}

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


@pytest.fixture(autouse=True)
def _reset_cache():
    _clear_keycloak_public_key_cache()
    yield
    _clear_keycloak_public_key_cache()


class TestIssuerValidation:
    """The JWT decode call must enforce the issuer claim."""

    @pytest.mark.asyncio
    async def test_invalid_issuer_rejected_as_401(self, mock_settings, mock_kc_key):
        # Simulate python-jose raising on issuer mismatch (what happens for real
        # when verify_iss=True and iss != expected).
        with patch(
            "src.auth.dependencies.jwt.decode",
            side_effect=JWTError("Invalid issuer"),
        ):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer forged"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_decode_receives_expected_issuer(self, mock_settings, mock_kc_key):
        captured: dict = {}

        def fake_decode(token, key, algorithms, issuer=None, options=None, **kw):
            captured["issuer"] = issuer
            captured["options"] = options
            return _base_payload()

        with patch("src.auth.dependencies.jwt.decode", side_effect=fake_decode):
            app = _make_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/me", headers={"Authorization": "Bearer ok"})
        assert resp.status_code == 200
        assert captured["issuer"] == "https://auth.gostoa.dev/realms/stoa"
        assert captured["options"]["verify_iss"] is True


class TestPublicKeyCache:
    """The realm public key must be cached; network call timeout must be set."""

    @pytest.mark.asyncio
    async def test_public_key_cached_between_calls(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"public_key": "MIIBIj..."})

        transport = httpx.MockTransport(handler)

        class _FakeClient(httpx.AsyncClient):
            def __init__(self, *a, **kw):
                super().__init__(*a, transport=transport, **kw)

        with (
            patch("src.auth.dependencies.httpx.AsyncClient", _FakeClient),
            patch("src.auth.dependencies.settings") as m,
        ):
            m.KEYCLOAK_URL = "https://auth.test"
            m.KEYCLOAK_REALM = "stoa"
            pem1 = await get_keycloak_public_key()
            pem2 = await get_keycloak_public_key()

        assert pem1 == pem2
        assert calls["n"] == 1, "second call must hit the cache"

    @pytest.mark.asyncio
    async def test_missing_public_key_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"public_key": None})

        transport = httpx.MockTransport(handler)

        class _FakeClient(httpx.AsyncClient):
            def __init__(self, *a, **kw):
                super().__init__(*a, transport=transport, **kw)

        with (
            patch("src.auth.dependencies.httpx.AsyncClient", _FakeClient),
            patch("src.auth.dependencies.settings") as m,
        ):
            m.KEYCLOAK_URL = "https://auth.test"
            m.KEYCLOAK_REALM = "stoa"
            with pytest.raises(httpx.HTTPError):
                await get_keycloak_public_key()
