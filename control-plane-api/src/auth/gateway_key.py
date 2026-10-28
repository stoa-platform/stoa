"""Shared X-Gateway-Key check for internal endpoints called by gateways.

Fail-closed: no configured key disables the endpoint (503), and a missing
or unknown key is rejected (401).
"""

import hmac
import logging

from fastapi import Header, HTTPException

from src.config import settings

logger = logging.getLogger(__name__)


def gateway_key_is_valid(presented_key: str | None, valid_keys: list[str]) -> bool:
    """Return True if presented_key matches one of valid_keys (constant-time per key)."""
    presented = (presented_key or "").encode()
    return bool(presented) and any(hmac.compare_digest(presented, key.encode()) for key in valid_keys)


def require_gateway_key(
    x_gateway_key: str | None = Header(None, alias="X-Gateway-Key"),
) -> None:
    """FastAPI dependency enforcing a valid X-Gateway-Key header."""
    valid_keys = settings.gateway_api_keys_list
    if not valid_keys:
        raise HTTPException(
            status_code=503,
            detail="Internal gateway endpoint disabled (no GATEWAY_API_KEYS configured)",
        )
    if not gateway_key_is_valid(x_gateway_key, valid_keys):
        logger.warning("Rejected internal gateway call with missing or invalid key")
        raise HTTPException(status_code=401, detail="Invalid gateway key")
