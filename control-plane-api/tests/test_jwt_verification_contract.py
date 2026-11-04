"""Library-independent access-token, DPoP and gateway assertion contracts."""

import base64
import hashlib
import importlib.util
import json
import os
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import urlencode

import pytest
from cryptography.hazmat.primitives import hashes, hmac, serialization as ser
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pytest_httpx import HTTPXMock

from src.auth.dependencies import User, _clear_keycloak_public_key_cache, get_current_user
from src.auth.sender_constrained import _jti_cache, validate_sender_constrained_token
from src.config import settings

ISSUER = "https://idp.example.test/realms/test"
URI = "https://api.example.test/me"
LEEWAY = 30  # Matches the gateway's JwtValidatorConfig.


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _public(key: rsa.RSAPrivateKey, encoding: ser.Encoding = ser.Encoding.PEM) -> bytes:
    return key.public_key().public_bytes(encoding, ser.PublicFormat.SubjectPublicKeyInfo)


def _jws(claims: dict[str, Any], key: Any, algorithm: str = "RS256", **headers: Any) -> str:
    parts = [_b64(json.dumps(part).encode()) for part in ({"alg": algorithm, **headers}, claims)]
    message = ".".join(parts).encode("ascii")
    if algorithm == "none":
        signature = b""
    elif algorithm == "HS256":
        mac = hmac.HMAC(key, hashes.SHA256())
        mac.update(message)
        signature = mac.finalize()
    elif algorithm in {"RS256", "PS256"}:
        scheme = padding.PKCS1v15() if algorithm == "RS256" else padding.PSS(padding.MGF1(hashes.SHA256()), 32)
        signature = key.sign(message, scheme, hashes.SHA256())
    elif algorithm == "ES256":
        r, s = decode_dss_signature(key.sign(message, ec.ECDSA(hashes.SHA256())))
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    else:
        assert algorithm == "EdDSA"
        signature = key.sign(message)
    return f"{message.decode()}.{_b64(signature)}"


def _corrupt(token: str) -> str:
    message, signature = token.rsplit(".", 1)
    raw = base64.urlsafe_b64decode(signature + "==")
    return f"{message}.{_b64(bytes([raw[0] ^ 1]) + raw[1:])}"


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    return {"sub": "contract-user", "iss": ISSUER, "aud": "control-plane-api", "iat": now, "exp": now + 300} | overrides


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def isolated_auth(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    config: dict[str, Any] = {"KEYCLOAK_URL": "https://idp.example.test", "KEYCLOAK_REALM": "test"}
    config.update(KEYCLOAK_INTERNAL_URL="https://idp.example.test", KEYCLOAK_CLIENT_ID="control-plane-api")
    config.update(STOA_DISABLE_AUTH=False, LOG_DEBUG_AUTH_TOKENS=False, LOG_DEBUG_AUTH_PAYLOAD=False)
    config.update(SENDER_CONSTRAINED_ENABLED=True, SENDER_CONSTRAINED_STRATEGY="auto")
    config.update(SENDER_CONSTRAINED_DPOP_MAX_CLOCK_SKEW=60)
    for name, value in config.items():
        monkeypatch.setattr(settings, name, value)
    _clear_keycloak_public_key_cache()
    _jti_cache.clear()
    yield
    _clear_keycloak_public_key_cache()
    _jti_cache.clear()


@pytest.fixture
async def client(signing_key: rsa.RSAPrivateKey, httpx_mock: HTTPXMock) -> AsyncIterator[AsyncClient]:
    httpx_mock.add_response(
        url=ISSUER,
        json={"public_key": base64.b64encode(_public(signing_key, ser.Encoding.DER)).decode()},
        is_optional=True,
    )
    app = FastAPI()

    @app.get("/me")
    async def me(user: User = Depends(get_current_user)) -> dict[str, str | None]:
        return {"id": user.id, "tenant_id": user.tenant_id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url=URI.removesuffix("/me")) as session:
        yield session


@pytest.mark.parametrize(
    "claim,value,status",
    [
        ("aud", "control-plane-api", 200),
        ("iss", "https://other.example.test", 401),
        ("iss", None, 401),
        ("aud", None, 401),
        ("aud", "other-api", 401),
        ("aud", [], 401),
        ("aud", ["other-api", "control-plane-api"], 200),
        ("aud", "stoa-mcp-gateway", 200),
        ("iat", None, 401),
        ("iat", "not-an-integer", 401),
        ("iat", LEEWAY // 3, 200),
        ("iat", LEEWAY * 4, 401),
        ("exp", None, 401),
        ("exp", -LEEWAY // 3, 200),
        ("exp", -LEEWAY * 4, 401),
        ("nbf", LEEWAY // 3, 200),
        ("nbf", LEEWAY * 4, 401),
    ],
)
async def test_access_claims(claim: str, value: Any, status: int, client: AsyncClient, signing_key: Any) -> None:
    claims = _claims()
    if value is None:
        claims.pop(claim)
    else:
        claims[claim] = int(time.time()) + value if claim in {"iat", "exp", "nbf"} and isinstance(value, int) else value
    response = await client.get("/me", headers={"Authorization": f"Bearer {_jws(claims, signing_key)}"})
    assert response.status_code == status
    if status == 401:
        # Exact match: neither the token claims nor the accepted audiences may be echoed.
        reason = "Invalid audience" if claim == "aud" else "verification failed"
        assert response.json() == {"detail": f"Invalid token: {reason}"}
    else:
        assert response.json()["id"] == "contract-user"


@pytest.mark.parametrize("case", ["none", "hs-pem", "hs-der", "rs-as-hs", "hs-as-rs", "tampered", "other-key"])
async def test_access_signatures(case: str, client: AsyncClient, signing_key: Any) -> None:
    public = _public(signing_key, ser.Encoding.DER if case == "hs-der" else ser.Encoding.PEM)
    if case == "none":
        token = _jws(_claims(), signing_key, "none")
    elif case.startswith("hs-"):
        token = _jws(_claims(), public, "HS256", **({"alg": "RS256"} if case == "hs-as-rs" else {}))
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if case == "other-key" else signing_key
        token = _jws(_claims(), key, **({"alg": "HS256"} if case == "rs-as-hs" else {}))
        if case == "tampered":
            token = _corrupt(token)
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    # Exact match: a leaked library message would fail this assertion.
    assert response.json() == {"detail": "Invalid token: verification failed"}


def _jwk(key: Any) -> dict[str, str]:
    if isinstance(key, rsa.RSAPrivateKey):
        rsa_numbers = key.public_key().public_numbers()
        fields = {
            name: _b64(v.to_bytes((v.bit_length() + 7) // 8, "big"))
            for name, v in {"n": rsa_numbers.n, "e": rsa_numbers.e}.items()
        }
        return {"kty": "RSA", **fields}
    if isinstance(key, ec.EllipticCurvePrivateKey):
        numbers = key.public_key().public_numbers()
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64(numbers.x.to_bytes(32, "big")),
            "y": _b64(numbers.y.to_bytes(32, "big")),
        }
    raw = key.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": _b64(raw)}


def _dpop(
    key: Any, alg: str = "RS256", overrides: dict[str, str] | None = None, corrupt: bool = False, signer: Any = None
) -> Any:
    """Build a proof whose header JWK is `key`'s public key; `signer` (default `key`) produces the signature."""
    public = _jwk(key)
    canonical = json.dumps(public, sort_keys=True, separators=(",", ":")).encode()
    claims: dict[str, Any] = {"htm": "GET", "htu": URI, "ath": _b64(hashlib.sha256(b"access-token").digest())}
    claims.update(jti="contract-proof", iat=int(time.time()) + 10)
    proof = _jws(claims, signer or key, alg, typ="dpop+jwt", jwk=public | (overrides or {}))
    return validate_sender_constrained_token(
        {"cnf": {"jkt": _b64(hashlib.sha256(canonical).digest())}},
        "access-token",
        {"dpop": _corrupt(proof) if corrupt else proof},
        "GET",
        URI,
    )


@pytest.mark.parametrize("alg", ["RS256", "ES256", "PS256", "EdDSA"])
def test_dpop_signed_proofs(alg: str, signing_key: Any) -> None:
    key = signing_key
    if alg == "ES256":
        key = ec.generate_private_key(ec.SECP256R1())
    elif alg == "EdDSA":
        key = ed25519.Ed25519PrivateKey.generate()
    result = _dpop(key, alg)
    assert result.valid, result.error
    assert result.mode == "dpop"


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"kty": "EC"}, "key type"),
        ({"crv": "P-384"}, "curve"),
        *[({member: "private-member"}, "public key material") for member in ("d", "p", "q", "dp", "dq", "qi")],
    ],
)
def test_dpop_key_policy(overrides: dict[str, str], error: str, signing_key: Any) -> None:
    key = ec.generate_private_key(ec.SECP256R1()) if "crv" in overrides else signing_key
    result = _dpop(key, "ES256" if "crv" in overrides else "RS256", overrides)
    assert not result.valid
    assert error in result.error


@pytest.mark.parametrize("alg", ["none", "HS256", "HS384", "HS512", "RS384", "ES384", "PS512", "unknown", None])
def test_dpop_algorithm_policy(alg: str | None) -> None:
    header = {"typ": "dpop+jwt", **({"alg": alg} if alg else {})}
    proof = f"{_b64(json.dumps(header).encode())}.{_b64(b'{}')}."
    result = validate_sender_constrained_token({"cnf": {"jkt": "unused"}}, "access-token", {"dpop": proof}, "GET", URI)
    assert not result.valid
    assert result.error == "DPoP proof algorithm is not supported"


@pytest.mark.parametrize("case", ["tampered", "other-key"])
def test_dpop_signature_rejections(case: str, signing_key: Any) -> None:
    """A corrupted signature or a proof signed by another key is rejected with stable text only."""
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    result = _dpop(signing_key, corrupt=case == "tampered", signer=other_key if case == "other-key" else None)
    assert not result.valid
    # Exact match: a leaked library message would fail this assertion.
    assert result.error == "DPoP validation failed"


@pytest.fixture(scope="module")
def gateway_endpoint(signing_key: Any) -> Any:
    """Import the real fixture module; its environment, path and socket setup do not leak, even on failure."""
    path = Path(__file__).resolve().parents[2] / "stoa-gateway/tests/fixtures/permission_control_plane.py"
    spec = importlib.util.spec_from_file_location("permission_control_plane", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        with mock.patch.dict(os.environ), mock.patch.object(sys, "path", list(sys.path)):
            spec.loader.exec_module(module)
    finally:
        if hasattr(module, "listener"):
            module.listener.close()
    pem = signing_key.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()).decode()
    vars(module).update(issuer=ISSUER, client_public_pem=_public(signing_key).decode(), pem=pem)
    return module.token


@pytest.mark.parametrize("case", ["valid", "aud", "iss", "sub", "jti", "signature", "grant"])
async def test_gateway_client_assertion(
    case: str, gateway_endpoint: Any, signing_key: Any, client: AsyncClient
) -> None:
    from fastapi import HTTPException

    claims = _claims(iss="stoa-mcp-gateway", sub="stoa-mcp-gateway", jti="client-assertion")
    claims["aud"] = f"{ISSUER}/protocol/openid-connect/token"
    if case in {"iss", "aud"}:
        claims[case] = "other"
    if case in {"sub", "jti"}:
        claims.pop(case)
    assertion = _jws(claims, signing_key)
    form = {"grant_type": "other" if case == "grant" else "client_credentials", "client_id": "stoa-mcp-gateway"}
    form.update(client_assertion_type="urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
    form["client_assertion"] = _corrupt(assertion) if case == "signature" else assertion

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": urlencode(form).encode()}

    request = Request({"type": "http", "method": "POST", "headers": []}, receive)
    if case != "valid":
        with pytest.raises(HTTPException) as exc:
            await gateway_endpoint(request)
        assert exc.value.status_code == (400 if case == "grant" else 401)
    else:
        result = await gateway_endpoint(request)
        assert result["expires_in"] == 300
        payload = json.loads(base64.urlsafe_b64decode(result["access_token"].split(".")[1] + "=="))
        assert payload["resource_access"]["control-plane-api"]["roles"] == ["gateway-tool-permissions-read"]
        response = await client.get("/me", headers={"Authorization": f"Bearer {result['access_token']}"})
        assert response.status_code == 200
        assert response.json() == {"id": "permission-reader", "tenant_id": "tenant-a"}
