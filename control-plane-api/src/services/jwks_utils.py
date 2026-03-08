"""JWKS utilities for FAPI key management (CAB-1748).

Converts PEM public keys to JWK format for Keycloak client-jwt authentication.
"""

import base64
import json
import logging
import uuid

from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1
from cryptography.hazmat.primitives.serialization import load_pem_public_key

logger = logging.getLogger(__name__)


def _int_to_base64url(n: int) -> str:
    """Convert an integer to a base64url-encoded string (no padding)."""
    byte_length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_length, byteorder="big")).rstrip(b"=").decode()


def pem_to_jwk(pem_data: str) -> dict:
    """Convert a PEM public key to JWK format.

    Supports RSA and EC (P-256) public keys.

    Args:
        pem_data: PEM-encoded public key string.

    Returns:
        JWK dict with standard fields (kty, n, e, etc.).

    Raises:
        ValueError: If the PEM is invalid or uses an unsupported key type.
    """
    pem_bytes = pem_data.strip().encode("utf-8")

    try:
        public_key = load_pem_public_key(pem_bytes)
    except Exception as e:
        raise ValueError(f"Invalid PEM public key: {e}") from e

    kid = str(uuid.uuid4())[:8]

    if isinstance(public_key, rsa.RSAPublicKey):
        numbers = public_key.public_numbers()
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": kid,
            "n": _int_to_base64url(numbers.n),
            "e": _int_to_base64url(numbers.e),
        }
    elif isinstance(public_key, ec.EllipticCurvePublicKey):
        numbers = public_key.public_numbers()
        if not isinstance(numbers.curve, SECP256R1):
            raise ValueError(f"Unsupported EC curve: {type(numbers.curve).__name__}. Use P-256.")
        # EC coordinates must be exactly 32 bytes for P-256
        x_bytes = numbers.x.to_bytes(32, byteorder="big")
        y_bytes = numbers.y.to_bytes(32, byteorder="big")
        return {
            "kty": "EC",
            "use": "sig",
            "alg": "ES256",
            "kid": kid,
            "crv": "P-256",
            "x": base64.urlsafe_b64encode(x_bytes).rstrip(b"=").decode(),
            "y": base64.urlsafe_b64encode(y_bytes).rstrip(b"=").decode(),
        }
    else:
        raise ValueError(f"Unsupported key type: {type(public_key).__name__}. Use RSA or EC P-256.")


def parse_jwks_input(raw_input: str) -> dict:
    """Parse a JWKS input — either PEM or JWK/JWKS JSON.

    Args:
        raw_input: Either a PEM string or a JSON string (JWK or JWKS).

    Returns:
        A JWKS dict: {"keys": [jwk1, ...]}.

    Raises:
        ValueError: If the input is neither valid PEM nor valid JWK JSON.
    """
    stripped = raw_input.strip()

    # Try PEM first
    if stripped.startswith("-----BEGIN"):
        jwk = pem_to_jwk(stripped)
        return {"keys": [jwk]}

    # Try JSON (JWK or JWKS)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ValueError(f"Input is neither valid PEM nor valid JSON: {e}") from e

    if isinstance(parsed, dict):
        if "keys" in parsed:
            # Already a JWKS
            return parsed
        if "kty" in parsed:
            # Single JWK — wrap in JWKS
            return {"keys": [parsed]}

    raise ValueError("JSON input must be a JWK object (with 'kty') or a JWKS object (with 'keys')")
