"""Credential Resolver — resolves Vault-backed gateway auth configs.

When a GatewayInstance stores vault_path in auth_config, this module fetches
the actual credentials from Vault before passing config to adapters.
Graceful fallback: if Vault is unavailable, the original auth_config is used as-is.
"""

import logging
from typing import Any

from src.adapters.registry import AdapterRegistry
from src.services.vault_client import get_vault_client

logger = logging.getLogger(__name__)


async def resolve_gateway_auth_config(auth_config: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve Vault-backed credentials in a gateway auth_config.

    If auth_config contains a 'vault_path' key, fetches secrets from Vault
    and merges them into the config. Vault values override existing keys.
    On Vault error, returns the original auth_config unchanged.
    """
    if not auth_config or "vault_path" not in auth_config:
        return auth_config or {}

    vault_path = auth_config["vault_path"]
    vault_client = get_vault_client()

    try:
        secrets = await vault_client.read_secret(vault_path)
    except Exception:
        logger.warning("Vault read failed for %s, using stored auth_config", vault_path)
        secrets = None

    if not secrets:
        logger.warning(
            "No Vault secrets at %s, falling back to stored auth_config",
            vault_path,
        )
        return {k: v for k, v in auth_config.items() if k != "vault_path"}

    resolved = {k: v for k, v in auth_config.items() if k != "vault_path"}
    resolved.update(secrets)
    logger.info("Resolved gateway credentials from Vault path %s", vault_path)
    return resolved


async def create_adapter_with_credentials(
    gateway_type: str,
    base_url: str,
    auth_config: dict[str, Any] | None,
    **extra_config: Any,
) -> Any:
    """Create a gateway adapter with Vault-resolved credentials.

    Convenience wrapper: resolves auth_config, then calls AdapterRegistry.create().
    """
    resolved_auth = await resolve_gateway_auth_config(auth_config)
    config = {"base_url": base_url, "auth_config": resolved_auth, **extra_config}
    return AdapterRegistry.create(gateway_type, config=config)
