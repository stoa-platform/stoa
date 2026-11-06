"""Regression tests for the fixed DPoP algorithm policy (CAB-2361)."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.auth.sender_constrained import (
    SenderConstrainedResult,
    _compute_ath,
    _compute_jwk_thumbprint,
    _jti_cache,
    _validate_dpop_binding,
)

URI = "https://api.example.test/v1/apis"
ACCESS_TOKEN = "test-access-token"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _integer(value: int) -> str:
    return _b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def _claims() -> dict:
    return {"htm": "GET", "htu": URI, "ath": _compute_ath(ACCESS_TOKEN), "jti": "cab-2361", "iat": int(time.time())}


def _compact(header: dict, key: bytes = b"", claims: dict | None = None) -> str:
    signing_input = (
        f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(_claims() if claims is None else claims).encode())}"
    )
    signature = hmac.new(key, signing_input.encode(), hashlib.sha256).digest() if key else b""
    return f"{signing_input}.{_b64(signature)}"


def _validate(proof: str, jwk: dict) -> SenderConstrainedResult:
    _jti_cache.clear()
    try:
        return _validate_dpop_binding({"jkt": _compute_jwk_thumbprint(jwk)}, {"dpop": proof}, ACCESS_TOKEN, "GET", URI)
    finally:
        _jti_cache.clear()


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize("encoding", [Encoding.PEM, Encoding.DER], ids=["pem", "der"])
def test_regression_cab_2361_dpop_hs256_public_key_rejected(rsa_key: rsa.RSAPrivateKey, encoding: Encoding) -> None:
    public_key = rsa_key.public_key()
    numbers = public_key.public_numbers()
    jwk = {"kty": "RSA", "n": _integer(numbers.n), "e": _integer(numbers.e)}
    key_bytes = public_key.public_bytes(encoding, PublicFormat.SubjectPublicKeyInfo)
    proof = _compact({"typ": "dpop+jwt", "alg": "HS256", "jwk": jwk}, key_bytes)

    result = _validate(proof, jwk)

    assert result.valid is False
    assert result.error == "DPoP proof algorithm is not supported"


@pytest.mark.parametrize(
    "algorithm", ["none", "HS256", "HS384", "HS512", "ES384", "RS384", "PS512", "PS256", "EdDSA", "unknown", None]
)
def test_regression_cab_2361_dpop_algorithm_rejected_before_jwk(algorithm: str | None) -> None:
    header = {"typ": "dpop+jwt", "alg": algorithm, "jwk": {"kty": "EC"}}
    if algorithm is None:
        del header["alg"]

    result = _validate_dpop_binding({"jkt": "unused"}, {"dpop": _compact(header)}, ACCESS_TOKEN, "GET", URI)

    assert result.valid is False
    assert result.error == "DPoP proof algorithm is not supported"


@pytest.mark.parametrize(("algorithm", "key_type"), [("ES256", "RSA"), ("ES256", "oct"), ("RS256", "EC")])
def test_regression_cab_2361_dpop_key_type_must_match_algorithm(algorithm: str, key_type: str) -> None:
    header = {"typ": "dpop+jwt", "alg": algorithm, "jwk": {"kty": key_type}}

    result = _validate_dpop_binding({"jkt": "unused"}, {"dpop": _compact(header)}, ACCESS_TOKEN, "GET", URI)

    assert result.valid is False
    assert result.error == "DPoP proof algorithm does not match JWK key type"


@pytest.mark.parametrize("member", ["d", "p", "q", "dp", "dq", "qi", "k"])
def test_regression_cab_2361_dpop_private_member_rejected_before_thumbprint(
    member: str, rsa_key: rsa.RSAPrivateKey
) -> None:
    numbers = rsa_key.public_key().public_numbers()
    jwk = {"kty": "RSA", "n": _integer(numbers.n), "e": _integer(numbers.e), member: ""}
    header = {"typ": "dpop+jwt", "alg": "RS256", "jwk": jwk}
    result = _validate_dpop_binding({"jkt": "unused"}, {"dpop": _compact(header)}, ACCESS_TOKEN, "GET", URI)
    assert result.valid is False
    assert result.error == "DPoP proof JWK must contain only public key material"


@pytest.mark.parametrize(
    ("algorithm", "curve_name", "iat_offset", "error"),
    [
        ("ES256", "P-256", 0, None),
        ("ES384", "P-384", 0, "DPoP proof algorithm is not supported"),
        ("ES256", "P-384", 0, "DPoP proof algorithm does not match JWK curve"),
        ("ES256", "P-256", None, "DPoP proof expired"),
        ("ES256", "P-256", -3600, "DPoP proof expired"),
    ],
)
def test_regression_cab_2361_dpop_signed_ec_algorithm_policy(
    algorithm: str, curve_name: str, iat_offset: int | None, error: str | None
) -> None:
    curve = ec.SECP256R1() if curve_name == "P-256" else ec.SECP384R1()
    private_key = ec.generate_private_key(curve)
    numbers = private_key.public_key().public_numbers()
    width = (curve.key_size + 7) // 8
    jwk = {
        "kty": "EC",
        "crv": curve_name,
        "x": _b64(numbers.x.to_bytes(width, "big")),
        "y": _b64(numbers.y.to_bytes(width, "big")),
    }
    claims = _claims()
    if iat_offset is None:
        del claims["iat"]
    else:
        claims["iat"] += iat_offset
    signing_input = _compact({"typ": "dpop+jwt", "alg": algorithm, "jwk": jwk}, claims=claims).rsplit(".", 1)[0]
    digest = hashes.SHA256() if algorithm == "ES256" else hashes.SHA384()
    r, s = decode_dss_signature(private_key.sign(signing_input.encode(), ec.ECDSA(digest)))
    signature = r.to_bytes(width, "big") + s.to_bytes(width, "big")
    proof = f"{signing_input}.{_b64(signature)}"

    result = _validate(proof, jwk)

    assert result.valid is (error is None)
    assert result.mode == "dpop"
    assert result.error is None if error is None else result.error.startswith(error)


def test_regression_cab_2361_dpop_rs256_accepted(rsa_key: rsa.RSAPrivateKey) -> None:
    numbers = rsa_key.public_key().public_numbers()
    jwk = {"kty": "RSA", "n": _integer(numbers.n), "e": _integer(numbers.e)}
    signing_input = _compact({"typ": "dpop+jwt", "alg": "RS256", "jwk": jwk}).rsplit(".", 1)[0]
    signature = rsa_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    proof = f"{signing_input}.{_b64(signature)}"

    result = _validate(proof, jwk)

    assert result.valid is True
    assert result.mode == "dpop"
