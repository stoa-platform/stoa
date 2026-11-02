"""Create API keys and persist only their hash."""

import hashlib
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models.api_key import ApiKey

KEY_PREFIX = "stoa_sk_"
_SECRET_BYTES = 16


def hash_key(raw_key: str) -> str:
    """SHA-256 hex digest of an API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext, hash, display prefix).

    The plaintext is shown to the caller once. Callers must not log it.
    """
    raw = KEY_PREFIX + secrets.token_hex(_SECRET_BYTES)
    # Fixed prefix plus 8 random characters, enough to tell keys apart.
    return raw, hash_key(raw), raw[: len(KEY_PREFIX) + 8]


async def create_api_key(
    db: AsyncSession,
    *,
    name: str,
    role: str,
    tenant_id: str,
) -> tuple[ApiKey, str]:
    """Persist a new key and return the row plus the one-time plaintext."""
    raw, digest, prefix = generate_api_key()
    record = ApiKey(
        name=name,
        role=role,
        tenant_id=tenant_id,
        key_hash=digest,
        key_prefix=prefix,
        revoked=False,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record, raw
