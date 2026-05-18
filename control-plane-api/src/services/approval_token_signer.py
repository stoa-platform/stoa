"""RS256 approval-token signing and JWKS exposure."""

import base64
import hashlib
from datetime import datetime
from typing import Any, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

RS256 = "RS256"


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class ApprovalTokenSigner:
    def __init__(self, *, signing_key: str, ttl_seconds: int) -> None:
        if not signing_key:
            raise ValueError("approval_token_signing_key is required")
        self.signing_key = signing_key
        self.ttl_seconds = ttl_seconds
        private_key = serialization.load_pem_private_key(signing_key.encode("utf-8"), password=None)
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise ValueError("approval_token_signing_key must be an RSA private key")
        self._public_key = private_key.public_key()
        public_pem = self.public_key_pem()
        self._kid = hashlib.sha256(public_pem.encode("utf-8")).hexdigest()[:16]

    def public_key_pem(self) -> str:
        public_bytes = cast(
            bytes,
            self._public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )
        return public_bytes.decode("utf-8")

    def sign(self, claims: dict[str, Any], *, issued_at: datetime, expires_at: datetime) -> str:
        payload = {
            **claims,
            "iss": "control-plane-api",
            "aud": "stoa-gateway",
            "iat": int(issued_at.timestamp()),
            "nbf": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return str(jwt.encode(payload, self.signing_key, algorithm=RS256, headers={"kid": self._kid}))

    def jwks(self) -> dict[str, Any]:
        numbers = self._public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": self._kid,
                    "alg": RS256,
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            ]
        }


def signer_from_settings(settings: Any) -> ApprovalTokenSigner:
    secret = settings.approval_token_signing_key
    signing_key = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    return ApprovalTokenSigner(signing_key=signing_key, ttl_seconds=settings.approval_token_ttl_seconds)
