"""HashiCorp Vault Client for External MCP Server Credentials.

Provides secure storage and retrieval of credentials for external MCP servers.
Uses Kubernetes authentication in cluster, token auth for development.

Graceful degradation: when Vault is unavailable or disabled, credential operations
return None/False instead of crashing. The MCP server feature works without Vault
(credentials just won't be persisted securely).
"""

import logging
import os
from typing import Any

import hvac
from hvac.exceptions import InvalidPath, VaultError

from src.config import settings

logger = logging.getLogger(__name__)


class VaultUnavailableError(Exception):
    """Raised when Vault is disabled or unreachable."""


class VaultSealedException(VaultError):
    """Raised when Vault is sealed and cannot serve requests."""

    def __init__(self) -> None:
        super().__init__("Vault is sealed — credentials unavailable. Check auto-unseal or unseal manually.")


class VaultClient:
    """HashiCorp Vault client for external MCP server credentials.

    Stores credentials at: secret/data/external-mcp-servers/{server_id}
    Gracefully degrades when Vault is unavailable (returns None instead of crashing).
    """

    def __init__(
        self,
        vault_addr: str,
        vault_token: str | None = None,
        kubernetes_role: str | None = None,
        mount_point: str = "secret",
        enabled: bool = True,
    ):
        self.vault_addr = vault_addr
        self.mount_point = mount_point
        self.enabled = enabled
        self._client: hvac.Client | None = None
        self._vault_token = vault_token
        self._kubernetes_role = kubernetes_role
        self._available: bool | None = None  # Cached availability after first check

    @property
    def is_available(self) -> bool:
        """Check if Vault is enabled and reachable."""
        if not self.enabled:
            return False
        if self._available is not None:
            return self._available
        self._available = self.health_check()
        return self._available

    def _get_client(self) -> hvac.Client:
        """Get or create authenticated Vault client."""
        if not self.enabled:
            raise VaultUnavailableError("Vault is disabled via VAULT_ENABLED=false")

        if self._client is not None and self._client.is_authenticated():
            return self._client

        self._client = hvac.Client(url=self.vault_addr)

        # Try Kubernetes auth first (in-cluster)
        if self._kubernetes_role:
            try:
                jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
                if os.path.exists(jwt_path):
                    with open(jwt_path) as f:
                        jwt_token = f.read()

                    self._client.auth.kubernetes.login(
                        role=self._kubernetes_role,
                        jwt=jwt_token,
                    )
                    logger.info("Authenticated with Vault using Kubernetes auth")
                    return self._client
            except Exception as e:
                logger.warning(f"Kubernetes auth failed, falling back to token: {e}")

        # Fall back to token auth (development)
        if self._vault_token:
            self._client.token = self._vault_token
            if self._client.is_authenticated():
                logger.info("Authenticated with Vault using token auth")
                return self._client

        raise VaultError("Failed to authenticate with Vault")

    def _ensure_unsealed(self) -> None:
        """Check Vault seal status before operations. Raises VaultSealedException if sealed."""
        try:
            client = self._get_client()
            status = client.sys.read_health_status(method="GET")
            if status.get("sealed", True):
                logger.error("Vault is sealed — credential operations will fail")
                raise VaultSealedException()
        except VaultSealedException:
            raise
        except Exception as e:
            logger.warning(f"Could not verify Vault seal status: {e}")

    async def store_credential(
        self,
        server_id: str,
        credentials: dict[str, Any],
    ) -> str | None:
        """Store credentials for an external MCP server.

        Returns the Vault path if stored, None if Vault is unavailable.
        """
        if not self.enabled:
            logger.warning("Vault disabled — credentials not stored for server %s", server_id)
            return None

        self._ensure_unsealed()
        client = self._get_client()
        path = f"external-mcp-servers/{server_id}"

        try:
            client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=credentials,
                mount_point=self.mount_point,
            )

            full_path = f"{self.mount_point}/data/{path}"
            logger.info(
                "Stored credentials for external MCP server in Vault",
                extra={"server_id": server_id, "path": full_path},
            )
            return full_path

        except VaultError as e:
            logger.error(
                "Failed to store credentials in Vault",
                extra={"server_id": server_id, "error": str(e)},
            )
            raise

    async def retrieve_credential(self, server_id: str) -> dict[str, Any] | None:
        """Retrieve credentials for an external MCP server.

        Returns credentials dict if found, None if not found or Vault unavailable.
        """
        if not self.enabled:
            logger.debug("Vault disabled — cannot retrieve credentials for server %s", server_id)
            return None

        self._ensure_unsealed()
        client = self._get_client()
        path = f"external-mcp-servers/{server_id}"

        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point,
            )

            if response and "data" in response and "data" in response["data"]:
                logger.info(
                    "Retrieved credentials from Vault",
                    extra={"server_id": server_id},
                )
                return response["data"]["data"]

            return None

        except InvalidPath:
            logger.warning(
                "Credentials not found in Vault",
                extra={"server_id": server_id},
            )
            return None

        except VaultError as e:
            logger.error(
                "Failed to retrieve credentials from Vault",
                extra={"server_id": server_id, "error": str(e)},
            )
            raise

    async def read_secret(self, path: str) -> dict[str, Any] | None:
        """Read a secret from any KV v2 path.

        Returns the secret data dict if found, None if not found or Vault unavailable.
        Unlike retrieve_credential(), accepts any path (not just external-mcp-servers/).
        """
        if not self.enabled:
            logger.debug("Vault disabled — cannot read secret at %s", path)
            return None

        self._ensure_unsealed()
        client = self._get_client()

        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point,
            )

            if response and "data" in response and "data" in response["data"]:
                logger.info("Read secret from Vault", extra={"path": path})
                return response["data"]["data"]

            return None

        except InvalidPath:
            logger.warning("Secret not found in Vault", extra={"path": path})
            return None

        except VaultError as e:
            logger.error("Failed to read secret from Vault", extra={"path": path, "error": str(e)})
            return None

    async def delete_credential(self, server_id: str) -> bool:
        """Delete credentials for an external MCP server.

        Returns True if deleted, False if not found or Vault unavailable.
        """
        if not self.enabled:
            logger.debug("Vault disabled — cannot delete credentials for server %s", server_id)
            return False

        self._ensure_unsealed()
        client = self._get_client()
        path = f"external-mcp-servers/{server_id}"

        try:
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point=self.mount_point,
            )

            logger.info(
                "Deleted credentials from Vault",
                extra={"server_id": server_id},
            )
            return True

        except InvalidPath:
            logger.warning(
                "Credentials not found for deletion",
                extra={"server_id": server_id},
            )
            return False

        except VaultError as e:
            logger.error(
                "Failed to delete credentials from Vault",
                extra={"server_id": server_id, "error": str(e)},
            )
            raise

    def health_check(self) -> bool:
        """Check if Vault is accessible and authenticated.

        Returns True if healthy, False otherwise. Never raises.
        """
        if not self.enabled:
            return False
        try:
            client = self._get_client()
            status = client.sys.read_health_status(method="GET")
            return status.get("sealed", True) is False
        except Exception:
            return False


# Global client instance
_vault_client: VaultClient | None = None


def get_vault_client() -> VaultClient:
    """Get or create the global Vault client instance.

    Uses settings from config.py (VAULT_ADDR, VAULT_TOKEN, etc.).
    """
    global _vault_client

    if _vault_client is None:
        _vault_client = VaultClient(
            vault_addr=settings.VAULT_ADDR,
            vault_token=settings.VAULT_TOKEN or None,
            kubernetes_role=settings.VAULT_KUBERNETES_ROLE,
            mount_point=settings.VAULT_MOUNT_POINT,
            enabled=settings.VAULT_ENABLED,
        )

    return _vault_client


async def shutdown_vault_client() -> None:
    """Cleanup Vault client resources."""
    global _vault_client
    _vault_client = None
