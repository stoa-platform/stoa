"""Issue compact JWS policy artifacts from a dedicated mounted Ed25519 key."""

import base64
import json
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from ..config import settings
from ..schemas.tool_permission_policy import MAX_POLICY_BYTES


def _b64url(value: bytes) -> bytes:
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail={"code": "policy_signing_unavailable"})


def sign_policy_artifact(payload: dict[str, Any]) -> str:
    """Sign a caller-validated payload; snapshot construction belongs to the caller.

    Configuration selects the dedicated key, never an algorithm or extra headers.
    Load on each issuance so an unavailable mount cannot reuse a cached key.
    """
    kid = settings.STOA_POLICY_SIGNING_KID
    if not re.fullmatch(r"cp-policy-[0-9]{4}(?:0[1-9]|1[0-2])-[1-9][0-9]*", kid):
        raise _unavailable()
    if not settings.STOA_POLICY_SIGNING_KEY_FILE:
        raise _unavailable()
    try:
        pem = Path(settings.STOA_POLICY_SIGNING_KEY_FILE).read_bytes()
        if not pem.startswith(b"-----BEGIN PRIVATE KEY-----"):
            raise _unavailable()
        key = serialization.load_pem_private_key(pem, password=None)
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm):
        # Neither exception text nor the mounted path belongs in responses or logs.
        raise _unavailable() from None
    if not isinstance(key, Ed25519PrivateKey):
        raise _unavailable()

    header = {"alg": "EdDSA", "typ": "stoa-tool-policy+jws", "kid": kid}
    protected = json.dumps(header, separators=(",", ":")).encode("utf-8")
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    signing_input = _b64url(protected) + b"." + _b64url(body)
    # A 64-byte Ed25519 signature takes 86 unpadded base64url characters.
    if len(signing_input) + 1 + 86 > MAX_POLICY_BYTES:
        raise HTTPException(status_code=413, detail={"code": "policy_artifact_too_large"})
    return (signing_input + b"." + _b64url(key.sign(signing_input))).decode("ascii")
