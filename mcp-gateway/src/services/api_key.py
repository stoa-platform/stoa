"""API Key Validation Service.

Validates API keys for server subscriptions.
Keys are stored as SHA-256 hashes in the subscription store.
"""

import hashlib
from datetime import datetime, timezone

import structlog

from ..middleware.auth import TokenClaims

logger = structlog.get_logger(__name__)

# In-memory store reference (same as handlers/servers.py)
# In production, this would query the database
_subscriptions: dict = {}


def get_subscriptions_store():
    """Get reference to the subscriptions store.

    This imports from handlers to share the same in-memory store.
    In production, this would be a database query.
    """
    from ..handlers.servers import _subscriptions
    return _subscriptions


async def validate_api_key(api_key: str) -> TokenClaims | None:
    """Validate an API key and return token claims if valid.

    Args:
        api_key: The full API key (stoa_sk_...)

    Returns:
        TokenClaims if valid, None otherwise
    """
    if not api_key or not api_key.startswith("stoa_sk_"):
        return None

    # Hash the provided key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_prefix = api_key[:16]

    # Get subscriptions store
    subscriptions = get_subscriptions_store()

    # Find subscription by key prefix (quick lookup)
    # Then verify the full hash
    for sub_id, subscription in subscriptions.items():
        if subscription.api_key_prefix == key_prefix:
            # TODO: In production, compare against stored hash in DB
            # For now, we accept if prefix matches (mock implementation)
            # The real implementation would:
            # 1. Lookup by prefix
            # 2. Compare full hash
            # 3. Check subscription status
            # 4. Check key expiration (grace period)

            # Check subscription status
            from ..models.server import ServerSubscriptionStatus
            if subscription.status != ServerSubscriptionStatus.ACTIVE:
                logger.warning(
                    "API key used for inactive subscription",
                    subscription_id=sub_id,
                    status=subscription.status,
                )
                return None

            # Update last used timestamp
            subscription.last_used_at = datetime.now(timezone.utc)

            logger.info(
                "API key validated successfully",
                subscription_id=sub_id,
                server_id=subscription.server_id,
                user_id=subscription.user_id,
            )

            # Build claims from subscription
            return TokenClaims(
                sub=subscription.user_id,
                preferred_username=f"api-key:{key_prefix}",
                client_id=subscription.server_id,
                azp=subscription.server_id,
                scope="mcp:invoke",
                # Include subscription context
                resource_access={
                    subscription.server_id: {
                        "roles": ["subscriber"],
                        "subscription_id": sub_id,
                        "tool_access": [
                            ta.tool_id for ta in subscription.tool_access
                            if ta.status.value == "enabled"
                        ],
                    }
                },
            )

    logger.warning("API key not found", key_prefix=key_prefix)
    return None


async def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage.

    Args:
        api_key: The plaintext API key

    Returns:
        SHA-256 hash of the key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


async def verify_api_key_hash(api_key: str, stored_hash: str) -> bool:
    """Verify an API key against a stored hash.

    Args:
        api_key: The plaintext API key to verify
        stored_hash: The stored SHA-256 hash

    Returns:
        True if the key matches, False otherwise
    """
    computed_hash = await hash_api_key(api_key)
    return computed_hash == stored_hash
