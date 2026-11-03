"""Credential Resolver — resolves Vault-backed gateway auth configs.

When a GatewayInstance stores vault_path in auth_config, this module fetches
the actual credentials from Vault before passing config to adapters.
Vault-backed configurations fail closed if credentials cannot be retrieved.
"""

import logging
from typing import Any

from src.adapters.registry import AdapterRegistry
from src.services.vault_client import get_vault_client

logger = logging.getLogger(__name__)

AGENT_MANAGED_MESSAGE = (
    "Gateway is agent-managed (source=self_register, type=stoa). " "Use the agent's heartbeat/sync-ack for status."
)

# Pure "stoa" gateways use the pull model. STOA Link/Connect registrations may
# also use STOA-specific gateway types while declaring deployment_mode=connect
# or topology=remote-agent; those are agent-managed too and must be acked by the
# agent instead of pushed from the Control Plane.
_PULL_MODEL_GATEWAY_TYPES = {"stoa"}
_PULL_MODEL_DEPLOYMENT_MODES = {"connect"}
_PULL_MODEL_TOPOLOGIES = {"remote-agent"}


class AgentManagedGatewayError(Exception):
    """Raised when an operation targets a pull-model agent-managed gateway.

    Only applies to gateway_type="stoa" (stoa-connect Go agent, pull model).
    stoa_sidecar and stoa_edge_mcp are push-capable and should NOT be blocked.
    """

    def __init__(self, gateway_name: str | None = None):
        detail = AGENT_MANAGED_MESSAGE
        if gateway_name:
            detail = f"Gateway '{gateway_name}': {detail}"
        super().__init__(detail)


class CredentialResolutionError(ValueError):
    """A required secret-store read failed; safe to expose to callers."""

    def __init__(self) -> None:
        super().__init__("Required read failed; no fallback credentials allowed; operation refused.")


async def resolve_gateway_auth_config(auth_config: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve Vault-backed credentials in a gateway auth_config.

    If auth_config contains a 'vault_path' key, fetches secrets from Vault
    and merges them into the config. Vault values override existing keys.
    Raises CredentialResolutionError if required credentials cannot be read.
    """
    if not auth_config or "vault_path" not in auth_config:
        return auth_config or {}

    vault_path = auth_config["vault_path"]
    try:
        vault_client = get_vault_client()
        secrets = await vault_client.read_secret(vault_path)
    except Exception:
        logger.warning("Secret store read failed; refusing gateway operation")
        raise CredentialResolutionError() from None

    if not secrets:
        logger.warning("Secret store returned no credentials; refusing gateway operation")
        raise CredentialResolutionError()

    resolved = {k: v for k, v in auth_config.items() if k != "vault_path"}
    resolved.update(secrets)
    logger.info("Resolved gateway credentials from secret store")
    return resolved


async def create_adapter_with_credentials(
    gateway_type: str,
    base_url: str,
    auth_config: dict[str, Any] | None,
    *,
    source: str | None = None,
    gateway_name: str | None = None,
    **extra_config: Any,
) -> Any:
    """Create a gateway adapter with Vault-resolved credentials.

    Convenience wrapper: resolves auth_config, then calls AdapterRegistry.create().

    Raises:
        AgentManagedGatewayError: if source is "self_register" AND gateway_type
            is "stoa" (pull-model agent). stoa_sidecar / stoa_edge_mcp are
            push-capable and should not be blocked.
        CredentialResolutionError: if required credentials cannot be retrieved.
    """
    deployment_mode = str(extra_config.get("deployment_mode") or "").strip().lower()
    topology = str(extra_config.get("topology") or "").strip().lower()
    if source == "self_register" and (
        gateway_type in _PULL_MODEL_GATEWAY_TYPES
        or deployment_mode in _PULL_MODEL_DEPLOYMENT_MODES
        or topology in _PULL_MODEL_TOPOLOGIES
    ):
        logger.info(
            "Blocked adapter creation for agent-managed gateway %s (type=%s)",
            gateway_name or "unknown",
            gateway_type,
        )
        raise AgentManagedGatewayError(gateway_name)

    resolved_auth = await resolve_gateway_auth_config(auth_config)
    logger.debug(
        "Creating %s adapter with auth keys: %s",
        gateway_type,
        list(resolved_auth.keys()) if resolved_auth else "none",
    )
    config = {"base_url": base_url, "auth_config": resolved_auth, **extra_config}
    return AdapterRegistry.create(gateway_type, config=config)
