"""Encryption service for backend API credentials (CAB-1188/CAB-1249).

Uses Fernet (AES-128-CBC with HMAC-SHA256) for symmetric encryption at-rest.
Key comes from BACKEND_ENCRYPTION_KEY; outside production a fixed dev key is used.
In production a missing key, or the public dev key set explicitly, is logged;
with BACKEND_ENCRYPTION_KEY_REQUIRED=true it stops startup instead, and a
malformed key is refused at startup too (see ensure_backend_encryption_key).
"""

import base64
import binascii
import hmac
import json
import logging

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None

# Development-only Fernet key: base64url(sha256("stoa-dev-encryption-key-not-for-production")),
# the key earlier versions derived at runtime, so dev data stays readable.
_DEV_FERNET_KEY = b"T8MPCzUWhMr2zAL4d7_LXxvIIIjcmXeQunrwfbwuXQ8="


_MISSING_KEY_MESSAGE = (
    "BACKEND_ENCRYPTION_KEY is not set or is the public dev key: backend credentials use the public dev key"
)


class BackendEncryptionKeyMissingError(RuntimeError):
    """Production runs without a private BACKEND_ENCRYPTION_KEY while the key is required."""

    def __init__(self) -> None:
        super().__init__(
            "BACKEND_ENCRYPTION_KEY is required in production (BACKEND_ENCRYPTION_KEY_REQUIRED=true); refusing to start"
        )


class BackendEncryptionKeyInvalidError(RuntimeError):
    """BACKEND_ENCRYPTION_KEY is set but is not a valid Fernet key (message never includes it)."""

    def __init__(self) -> None:
        super().__init__("BACKEND_ENCRYPTION_KEY is not a valid Fernet key; refusing to start")


def _is_public_dev_key(key: str | bytes) -> bool:
    """True when key is the development key published in this repository.

    Compares the decoded key bytes, decoded the way Fernet decodes its key.
    """
    raw = key.encode() if isinstance(key, str) else key
    try:
        decoded = base64.urlsafe_b64decode(raw.strip())
    except (binascii.Error, ValueError):
        return False
    return hmac.compare_digest(decoded, base64.urlsafe_b64decode(_DEV_FERNET_KEY))


def _key_missing_in_production() -> bool:
    """Production without a private key: unset, or set to the public dev key."""
    if settings.ENVIRONMENT != "production":
        return False
    key = settings.BACKEND_ENCRYPTION_KEY
    return not key or _is_public_dev_key(key)


def ensure_backend_encryption_key() -> None:
    """Startup check for the backend encryption key.

    Production without a private key (unset, or the public dev key) always
    logs an error. It raises only when BACKEND_ENCRYPTION_KEY_REQUIRED is
    true, so the default keeps today's behaviour (a deployment without the
    secret can still read what it stored). When required, a key that is set
    must also be a valid Fernet key.
    """
    if _key_missing_in_production():
        logger.error(_MISSING_KEY_MESSAGE)
        if settings.BACKEND_ENCRYPTION_KEY_REQUIRED:
            raise BackendEncryptionKeyMissingError()
        return
    key = settings.BACKEND_ENCRYPTION_KEY
    if settings.BACKEND_ENCRYPTION_KEY_REQUIRED and key:
        try:
            Fernet(key.encode())
        except (ValueError, TypeError):
            raise BackendEncryptionKeyInvalidError() from None


def _get_fernet() -> Fernet:
    """Get or create Fernet instance from settings."""
    global _fernet
    if _fernet is None:
        key = settings.BACKEND_ENCRYPTION_KEY
        if _key_missing_in_production():
            # The dev key is public (it is in this repository). Refused only
            # when BACKEND_ENCRYPTION_KEY_REQUIRED is set: otherwise a
            # deployment without the secret would lose access to what it
            # already stored. Set BACKEND_ENCRYPTION_KEY from Vault.
            if settings.BACKEND_ENCRYPTION_KEY_REQUIRED:
                raise BackendEncryptionKeyMissingError()
            logger.error(_MISSING_KEY_MESSAGE)
            key = _DEV_FERNET_KEY
        elif not key:
            key = _DEV_FERNET_KEY
        elif isinstance(key, str):
            # If it's a base64 Fernet key, use directly
            key = key.encode()
        _fernet = Fernet(key)
    return _fernet


def encrypt_auth_config(auth_config: dict) -> str:
    """Encrypt auth config dict to a base64 string for DB storage."""
    plaintext = json.dumps(auth_config).encode("utf-8")
    return _get_fernet().encrypt(plaintext).decode("utf-8")


def decrypt_auth_config(encrypted: str) -> dict:
    """Decrypt auth config from DB storage back to dict."""
    try:
        plaintext = _get_fernet().decrypt(encrypted.encode("utf-8"))
        return json.loads(plaintext.decode("utf-8"))
    except InvalidToken:
        logger.error("Failed to decrypt auth config — invalid token or key mismatch")
        raise ValueError("Cannot decrypt backend credentials — encryption key may have changed")
