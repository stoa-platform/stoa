"""CAB-2353: real RS256 verification preserves the authentication HTTP contract."""

import time
from contextlib import nullcontext
from functools import partial

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response

from src.auth import dependencies
from src.auth.dependencies import User, get_current_user
from src.auth.jwt_claims import validate_legacy_claims


@pytest.fixture(scope="module")
def signing_keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPrivateKey]:
    """Synthetic private keys stay in memory and never reach logs or fixtures."""
    return tuple(rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_status"),
    [
        ("valid", 200),
        ("future_iat", 200),
        ("expired", 401),
        ("bad_signature", 401),
        ("bad_audience", 401),
        ("bad_issuer", 401),
        ("future_nbf", 401),
        ("invalid_iat", 401),
        ("at_hash", 401),
        ("bad_key", 401),
    ],
)
async def test_regression_cab_2353_jwt_authentication(
    case: str,
    expected_status: int,
    signing_keys: tuple[rsa.RSAPrivateKey, rsa.RSAPrivateKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise real token decoding and realm-key fetch through HTTP transports."""
    issuer = "https://issuer.example.test/realms/test"
    for name, value in {
        "KEYCLOAK_URL": "https://issuer.example.test",
        "KEYCLOAK_INTERNAL_URL": "https://issuer.example.test",
        "KEYCLOAK_REALM": "test",
        "KEYCLOAK_CLIENT_ID": "control-plane-api",
        "LOG_DEBUG_AUTH_TOKENS": False,
        "LOG_DEBUG_AUTH_PAYLOAD": False,
        "STOA_DISABLE_AUTH": False,
        "SENDER_CONSTRAINED_ENABLED": False,
    }.items():
        monkeypatch.setattr(dependencies.settings, name, value)
    monkeypatch.setattr(dependencies, "_KC_PUBLIC_KEY_CACHE", {})
    public_pem = (
        signing_keys[0]
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    public_body = "".join(public_pem.decode().splitlines()[1:-1])
    if case == "bad_key":
        public_body = "malformed-public-key"
    fetched_urls: list[str] = []

    def realm_key(request: Request) -> Response:
        fetched_urls.append(str(request.url))
        assert request.method == "GET"
        assert str(request.url) == issuer
        return Response(200, json={"public_key": public_body})

    monkeypatch.setattr(dependencies.httpx, "AsyncClient", partial(AsyncClient, transport=MockTransport(realm_key)))
    now = int(time.time())
    claims = {
        "sub": "cab-2353-user",
        "email": "cab-2353@example.test",
        "preferred_username": "cab-2353",
        "realm_access": {"roles": ["viewer"]},
        "tenant_id": "test-tenant",
        "aud": ["control-plane-api"],
        "iss": issuer,
        "exp": now - 3600 if case == "expired" else now + 3600,
        "iat": now + 3600 if case == "future_iat" else now - 60,
        "nbf": now + 3600 if case == "future_nbf" else now - 60,
    }
    if case == "bad_audience":
        claims["aud"] = ["another-api"]
    if case == "bad_issuer":
        claims["iss"] = "https://untrusted.example.test/realms/test"
    if case == "invalid_iat":
        claims["iat"] = "invalid"
    if case == "at_hash":
        claims["at_hash"] = "requires-access-token-validation"
    token = jwt.encode(claims, signing_keys[case == "bad_signature"], algorithm="RS256")
    app = FastAPI()

    @app.get("/me")
    async def me(user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"id": user.id, "username": user.username}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert fetched_urls == [issuer]
    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json() == {"id": "cab-2353-user", "username": "cab-2353"}
    else:
        assert response.json()["detail"].startswith("Invalid token: ")


@pytest.mark.parametrize(
    ("claims", "error"),
    [
        ({"exp": 1000}, None),
        ({"exp": 999}, jwt.ExpiredSignatureError),
        ({"exp": 1001}, None),
        ({}, None),
        ({"exp": "invalid"}, jwt.InvalidTokenError),
    ],
)
def test_regression_cab_2353_integer_second_expiry(
    claims: dict[str, int | str], error: type[Exception] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.auth.jwt_claims.time.time", lambda: 1000.75)
    with pytest.raises(error) if error else nullcontext():
        validate_legacy_claims(claims)
