"""Encryption service for backend API credentials (CAB-1188/CAB-1249).

Uses Fernet (AES-128-CBC with HMAC-SHA256) for symmetric encryption at-rest.
Key comes from BACKEND_ENCRYPTION_KEY; outside production a fixed dev key is used.
In production a missing key is logged; with BACKEND_ENCRYPTION_KEY_REQUIRED=true
it stops startup instead (see ensure_backend_encryption_key).
"""

import json
import logging

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None

# Development-only Fernet key: base64url(sha256("stoa-dev-encryption-key-not-for-production")),
# the key earlier versions derived at runtime, so dev data stays readable.
_DEV_FERNET_KEY = b"T8MPCzUWhMr2zAL4d7_LXxvIIIjcmXeQunrwfbwuXQ8="


_MISSING_KEY_MESSAGE = "BACKEND_ENCRYPTION_KEY is not set: backend credentials use the public dev key"


class BackendEncryptionKeyMissingError(RuntimeError):
    """Production runs without BACKEND_ENCRYPTION_KEY while the key is required."""

    def __init__(self) -> None:
        super().__init__(
            "BACKEND_ENCRYPTION_KEY is required in production (BACKEND_ENCRYPTION_KEY_REQUIRED=true); refusing to start"
        )


def _key_missing_in_production() -> bool:
    return not settings.BACKEND_ENCRYPTION_KEY and settings.ENVIRONMENT == "production"


def ensure_backend_encryption_key() -> None:
    """Startup check for the backend encryption key.

    Production without a key always logs an error. It raises only when
    BACKEND_ENCRYPTION_KEY_REQUIRED is true, so the default keeps today's
    behaviour (a deployment without the secret can still read what it stored).
    """
    if not _key_missing_in_production():
        return
    logger.error(_MISSING_KEY_MESSAGE)
    if settings.BACKEND_ENCRYPTION_KEY_REQUIRED:
        raise BackendEncryptionKeyMissingError()


def _get_fernet() -> Fernet:
    """Get or create Fernet instance from settings."""
    global _fernet
    if _fernet is None:
        key = settings.BACKEND_ENCRYPTION_KEY
        if not key:
            if _key_missing_in_production():
                # The dev key is public (it is in this repository). Refused only
                # when BACKEND_ENCRYPTION_KEY_REQUIRED is set: otherwise a
                # deployment without the secret would lose access to what it
                # already stored. Set BACKEND_ENCRYPTION_KEY from Vault.
                if settings.BACKEND_ENCRYPTION_KEY_REQUIRED:
                    raise BackendEncryptionKeyMissingError()
                logger.error(_MISSING_KEY_MESSAGE)
            key = _DEV_FERNET_KEY
        elif isinstance(key, str):
            # If it's a base64 Fernet key, use directly
            key = key.encode() if isinstance(key, str) else key
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
