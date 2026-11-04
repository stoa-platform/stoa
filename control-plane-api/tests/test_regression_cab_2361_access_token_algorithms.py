"""CAB-2361: access token verification keeps a fixed RS256 algorithm."""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pytest_httpx import HTTPXMock

from src.auth.dependencies import User, _clear_keycloak_public_key_cache, get_current_user
from src.config import settings


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@pytest.fixture
def idp_signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def configure_auth(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "KEYCLOAK_URL", "https://idp.example.test")
    monkeypatch.setattr(settings, "KEYCLOAK_INTERNAL_URL", "https://idp.example.test")
    monkeypatch.setattr(settings, "KEYCLOAK_REALM", "test-realm")
    monkeypatch.setattr(settings, "KEYCLOAK_CLIENT_ID", "control-plane-api")
    monkeypatch.setattr(settings, "STOA_DISABLE_AUTH", False)
    monkeypatch.setattr(settings, "LOG_DEBUG_AUTH_TOKENS", False)
    monkeypatch.setattr(settings, "LOG_DEBUG_AUTH_PAYLOAD", False)
    monkeypatch.setattr(settings, "SENDER_CONSTRAINED_ENABLED", True)
    monkeypatch.setattr(settings, "SENDER_CONSTRAINED_STRATEGY", "auto")
    _clear_keycloak_public_key_cache()
    yield
    _clear_keycloak_public_key_cache()


def _public_key_bytes(key: rsa.RSAPrivateKey, encoding: serialization.Encoding) -> bytes:
    value = key.public_key().public_bytes(encoding, serialization.PublicFormat.SubjectPublicKeyInfo)
    return value.strip() if encoding == serialization.Encoding.PEM else value


def _signing_input(algorithm: str) -> bytes:
    now = int(time.time())
    claims = {
        "sub": "cab-2361-user",
        "email": "user@example.test",
        "preferred_username": "test-user",
        "realm_access": {"roles": ["viewer"]},
        "aud": "control-plane-api",
        "iss": "https://idp.example.test/realms/test-realm",
        "iat": now,
        "exp": now + 300,
    }
    header = _base64url(json.dumps({"alg": algorithm, "typ": "JWT"}).encode())
    payload = _base64url(json.dumps(claims).encode())
    return f"{header}.{payload}".encode("ascii")


async def _authenticate(token: str, key: rsa.RSAPrivateKey, httpx_mock: HTTPXMock) -> User:
    pem_lines = _public_key_bytes(key, serialization.Encoding.PEM).decode().splitlines()
    httpx_mock.add_response(
        url="https://idp.example.test/realms/test-realm",
        json={"public_key": "\n".join(pem_lines[1:-1])},
    )
    request = Request({"type": "http", "method": "GET", "scheme": "https", "path": "/me", "headers": []})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return await get_current_user(request, credentials)


@pytest.mark.parametrize("encoding", [serialization.Encoding.PEM, serialization.Encoding.DER], ids=["pem", "der"])
async def test_regression_cab_2361_access_token_hs256_rejected(
    encoding: serialization.Encoding, idp_signing_key: rsa.RSAPrivateKey, httpx_mock: HTTPXMock
) -> None:
    signing_input = _signing_input("HS256")
    signature = hmac.new(_public_key_bytes(idp_signing_key, encoding), signing_input, hashlib.sha256).digest()
    token = f"{signing_input.decode()}.{_base64url(signature)}"

    with pytest.raises(HTTPException) as exc_info:
        await _authenticate(token, idp_signing_key, httpx_mock)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token: verification failed"


async def test_regression_cab_2361_access_token_rs256_accepted(
    idp_signing_key: rsa.RSAPrivateKey, httpx_mock: HTTPXMock
) -> None:
    signing_input = _signing_input("RS256")
    signature = idp_signing_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    token = f"{signing_input.decode()}.{_base64url(signature)}"

    user = await _authenticate(token, idp_signing_key, httpx_mock)

    assert user.id == "cab-2361-user"
    assert user.roles == ["viewer"]
