"""Encryption service for backend API credentials (CAB-1188/CAB-1249).

Uses Fernet (AES-128-CBC with HMAC-SHA256) for symmetric encryption at-rest.
Key is derived from BACKEND_ENCRYPTION_KEY env var or a default for dev.
"""

import base64
import hashlib
import json
import logging

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Get or create Fernet instance from settings."""
    global _fernet
    if _fernet is None:
        key = settings.BACKEND_ENCRYPTION_KEY
        if not key:
            # Derive a key from a passphrase for dev environments
            passphrase = "stoa-dev-encryption-key-not-for-production"
            derived = hashlib.sha256(passphrase.encode()).digest()
            key = base64.urlsafe_b64encode(derived)
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
