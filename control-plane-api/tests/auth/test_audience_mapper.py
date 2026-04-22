"""Evidence test for CAB-2153 — JWT audience validation via Audience Mapper.

Parent: CAB-2148 (demo kernel). Related: CAB-2079 (scoped subset).

Scope
-----
The MCP Gateway client (``stoa-mcp-gateway``) in the Keycloak realm must be
configured with an Audience Mapper so that tokens it issues carry
``control-plane-api`` (the Resource Server identifier) in their ``aud`` claim.
Legacy tokens whose ``aud`` is the client id itself — e.g. ``stoa-mcp-gateway``
or ``stoa-portal`` — must still be accepted during the migration window so the
demo has a Mode A (live path) and a Mode B (fallback) per CAB-2151.

This test is an **evidence test** — it proves the validation path at
``control-plane-api/src/auth/dependencies.py:176`` accepts the correct
audiences and rejects everything else, using **real** RS256 JWTs signed with an
RSA keypair (no ``jwt.decode`` mocking). If this passes, the demo runs Mode A.

Boundary integrity
------------------
- The JWT is signed by a real RSA keypair and decoded by the real ``jose``
  library. Only the public-key fetch is short-circuited (so we don't need a
  live Keycloak) and the sender-constrained validator is bypassed (it is
  disabled by default in ``Settings.SENDER_CONSTRAINED_ENABLED=False``).
- The Audience Mapper itself is a Keycloak-side config artefact — we ship it
  via a realm JSON patch + a kcadm migration script; the test here proves the
  **consumer side** (cp-api) honours the resulting ``aud`` claim.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt as jose_jwt

from src.auth.dependencies import User, get_current_user

# --- Fixtures ---------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, str]:
    """Generate an RSA keypair once per module for signing/verifying JWTs."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def _sign(private_pem: str, claims: dict[str, Any]) -> str:
    """Sign a JWT with RS256 using the private PEM key (real ``jose`` encode)."""
    token: str = jose_jwt.encode(claims, private_pem, algorithm="RS256")
    return token


def _base_claims(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sub": "user-cab-2153",
        "email": "evidence@cab2153.test",
        "preferred_username": "evidence",
        "realm_access": {"roles": ["viewer"]},
        "tenant_id": "demo",
        "aud": ["control-plane-api"],
        "azp": "stoa-mcp-gateway",
        "iss": "https://auth.gostoa.dev/realms/stoa",
    }
    base.update(overrides)
    return base


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/me")
    async def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
        return {"id": user.id, "roles": user.roles, "tenant_id": user.tenant_id}

    return app


@pytest.fixture
def patched_settings() -> Any:
    """Pin cp-api settings to match the signed token ``iss`` and expected aud."""
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
def patched_public_key(rsa_keypair: tuple[str, str]) -> Any:
    """Serve the RSA public key the test JWTs are signed with."""
    _, public_pem = rsa_keypair
    with patch(
        "src.auth.dependencies.get_keycloak_public_key",
        new_callable=AsyncMock,
    ) as m:
        m.return_value = public_pem
        yield m


# --- Tests ------------------------------------------------------------------


class TestRegressionCab2153AudienceMapper:
    """Evidence suite for the Audience Mapper landing on ``stoa-mcp-gateway``."""

    @pytest.mark.asyncio
    async def test_regression_cab_2153_audience_control_plane_api_accepted(
        self,
        rsa_keypair: tuple[str, str],
        patched_settings: Any,
        patched_public_key: Any,
    ) -> None:
        """Mode A: token with aud=control-plane-api (mapper present) -> 200.

        This is the DoD evidence for the Audience Mapper: once the mapper is
        deployed on ``stoa-mcp-gateway``, its tokens carry
        ``aud=["control-plane-api"]`` and this path must succeed.
        """
        private_pem, _ = rsa_keypair
        token = _sign(private_pem, _base_claims(aud=["control-plane-api"]))

        async with AsyncClient(
            transport=ASGITransport(app=_make_app()), base_url="http://t"
        ) as client:
            resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == "user-cab-2153"

    @pytest.mark.asyncio
    async def test_regression_cab_2153_audience_wrong_rejected_at_dependencies_176(
        self,
        rsa_keypair: tuple[str, str],
        patched_settings: Any,
        patched_public_key: Any,
    ) -> None:
        """Negative: token with an unexpected aud must be rejected at :176."""
        private_pem, _ = rsa_keypair
        token = _sign(
            private_pem,
            _base_claims(aud=["some-other-api"], azp="stoa-mcp-gateway"),
        )

        async with AsyncClient(
            transport=ASGITransport(app=_make_app()), base_url="http://t"
        ) as client:
            resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 401
        assert "Invalid token" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_regression_cab_2153_audience_legacy_mcp_gateway_accepted_with_deprecation(
        self,
        rsa_keypair: tuple[str, str],
        patched_settings: Any,
        patched_public_key: Any,
    ) -> None:
        """Mode B fallback: pre-mapper MCP token (aud=stoa-mcp-gateway) -> 200.

        Without the Audience Mapper, Keycloak sets ``aud=<client-id>``. The
        demo must still authenticate in that state so CAB-2151's binary gate
        has a fallback; a deprecation warning is emitted server-side.
        """
        private_pem, _ = rsa_keypair
        token = _sign(
            private_pem,
            _base_claims(aud=["stoa-mcp-gateway"], azp="stoa-mcp-gateway"),
        )

        async with AsyncClient(
            transport=ASGITransport(app=_make_app()), base_url="http://t"
        ) as client:
            resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_regression_cab_2153_audience_list_mixed_accepts_on_primary(
        self,
        rsa_keypair: tuple[str, str],
        patched_settings: Any,
        patched_public_key: Any,
    ) -> None:
        """Audience list containing the primary audience is accepted."""
        private_pem, _ = rsa_keypair
        token = _sign(
            private_pem,
            _base_claims(aud=["control-plane-api", "account"]),
        )

        async with AsyncClient(
            transport=ASGITransport(app=_make_app()), base_url="http://t"
        ) as client:
            resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200, resp.text
