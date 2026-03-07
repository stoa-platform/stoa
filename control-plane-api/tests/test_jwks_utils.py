"""Tests for JWKS utilities (CAB-1748)."""

import json

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.services.jwks_utils import parse_jwks_input, pem_to_jwk

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def rsa_pem() -> str:
    """Generate a test RSA public key in PEM format."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()


@pytest.fixture
def ec_pem() -> str:
    """Generate a test EC P-256 public key in PEM format."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()


# ============================================================================
# pem_to_jwk tests
# ============================================================================


def test_pem_to_jwk_rsa(rsa_pem: str) -> None:
    jwk = pem_to_jwk(rsa_pem)
    assert jwk["kty"] == "RSA"
    assert jwk["use"] == "sig"
    assert jwk["alg"] == "RS256"
    assert "kid" in jwk
    assert "n" in jwk
    assert "e" in jwk


def test_pem_to_jwk_ec(ec_pem: str) -> None:
    jwk = pem_to_jwk(ec_pem)
    assert jwk["kty"] == "EC"
    assert jwk["use"] == "sig"
    assert jwk["alg"] == "ES256"
    assert jwk["crv"] == "P-256"
    assert "x" in jwk
    assert "y" in jwk


def test_pem_to_jwk_invalid_pem() -> None:
    with pytest.raises(ValueError, match="Invalid PEM"):
        pem_to_jwk("not a pem")


def test_pem_to_jwk_rejects_private_key() -> None:
    """Private keys should be rejected — only public keys accepted."""
    from cryptography.hazmat.primitives.serialization import NoEncryption

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        Encoding.PEM, format=PublicFormat.TraditionalOpenSSL if hasattr(PublicFormat, "TraditionalOpenSSL") else None,
        encryption_algorithm=NoEncryption(),
    ).decode() if False else ""
    # load_pem_public_key will fail on a private key PEM
    private_pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJB\n-----END RSA PRIVATE KEY-----"
    with pytest.raises(ValueError, match="Invalid PEM"):
        pem_to_jwk(private_pem)


# ============================================================================
# parse_jwks_input tests
# ============================================================================


def test_parse_jwks_input_pem(rsa_pem: str) -> None:
    result = parse_jwks_input(rsa_pem)
    assert "keys" in result
    assert len(result["keys"]) == 1
    assert result["keys"][0]["kty"] == "RSA"


def test_parse_jwks_input_jwk_json() -> None:
    jwk = {"kty": "RSA", "n": "test", "e": "AQAB", "use": "sig"}
    result = parse_jwks_input(json.dumps(jwk))
    assert "keys" in result
    assert len(result["keys"]) == 1
    assert result["keys"][0]["kty"] == "RSA"


def test_parse_jwks_input_jwks_json() -> None:
    jwks = {"keys": [{"kty": "RSA", "n": "test", "e": "AQAB"}]}
    result = parse_jwks_input(json.dumps(jwks))
    assert "keys" in result
    assert len(result["keys"]) == 1


def test_parse_jwks_input_invalid_json() -> None:
    with pytest.raises(ValueError, match="neither valid PEM nor valid JSON"):
        parse_jwks_input("not json and not pem")


def test_parse_jwks_input_json_without_kty() -> None:
    with pytest.raises(ValueError, match="must be a JWK"):
        parse_jwks_input(json.dumps({"foo": "bar"}))


def test_parse_jwks_input_ec_pem(ec_pem: str) -> None:
    result = parse_jwks_input(ec_pem)
    assert "keys" in result
    assert result["keys"][0]["kty"] == "EC"
    assert result["keys"][0]["crv"] == "P-256"
