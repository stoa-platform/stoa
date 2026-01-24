"""HashiCorp Vault Client for External MCP Server Credentials.

Provides secure storage and retrieval of credentials for external MCP servers.
Uses Kubernetes authentication in cluster, token auth for development.

Reference: External MCP Server Registration Plan
"""
import os
import logging
from functools import lru_cache
from typing import Any, Optional

import hvac
from hvac.exceptions import VaultError, InvalidPath

from src.config import settings

logger = logging.getLogger(__name__)


class VaultClient:
    """HashiCorp Vault client for external MCP server credentials.

    Stores credentials at: secret/data/external-mcp-servers/{server_id}
    """

    def __init__(
        self,
        vault_addr: str,
        vault_token: Optional[str] = None,
        kubernetes_role: Optional[str] = None,
        mount_point: str = "secret",
    ):
        """Initialize Vault client.

        Args:
            vault_addr: Vault server URL (e.g., https://vault.gostoa.dev)
            vault_token: Vault token for authentication (dev mode)
            kubernetes_role: Kubernetes auth role name (production)
            mount_point: KV secrets engine mount point
        """
        self.vault_addr = vault_addr
        self.mount_point = mount_point
        self._client: Optional[hvac.Client] = None
        self._vault_token = vault_token
        self._kubernetes_role = kubernetes_role

    def _get_client(self) -> hvac.Client:
        """Get or create authenticated Vault client."""
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

    async def store_credential(
        self,
        server_id: str,
        credentials: dict[str, Any],
    ) -> str:
        """Store credentials for an external MCP server.

        Args:
            server_id: External MCP server ID
            credentials: Credential data (api_key, bearer_token, or oauth2 config)

        Returns:
            The Vault path where credentials are stored
        """
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
                f"Stored credentials for external MCP server in Vault",
                extra={"server_id": server_id, "path": full_path},
            )
            return full_path

        except VaultError as e:
            logger.error(
                f"Failed to store credentials in Vault",
                extra={"server_id": server_id, "error": str(e)},
            )
            raise

    async def retrieve_credential(self, server_id: str) -> Optional[dict[str, Any]]:
        """Retrieve credentials for an external MCP server.

        Args:
            server_id: External MCP server ID

        Returns:
            Credentials dict if found, None otherwise
        """
        client = self._get_client()
        path = f"external-mcp-servers/{server_id}"

        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point,
            )

            if response and "data" in response and "data" in response["data"]:
                logger.info(
                    f"Retrieved credentials from Vault",
                    extra={"server_id": server_id},
                )
                return response["data"]["data"]

            return None

        except InvalidPath:
            logger.warning(
                f"Credentials not found in Vault",
                extra={"server_id": server_id},
            )
            return None

        except VaultError as e:
            logger.error(
                f"Failed to retrieve credentials from Vault",
                extra={"server_id": server_id, "error": str(e)},
            )
            raise

    async def delete_credential(self, server_id: str) -> bool:
        """Delete credentials for an external MCP server.

        Args:
            server_id: External MCP server ID

        Returns:
            True if deleted, False if not found
        """
        client = self._get_client()
        path = f"external-mcp-servers/{server_id}"

        try:
            # Permanently delete all versions
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point=self.mount_point,
            )

            logger.info(
                f"Deleted credentials from Vault",
                extra={"server_id": server_id},
            )
            return True

        except InvalidPath:
            logger.warning(
                f"Credentials not found for deletion",
                extra={"server_id": server_id},
            )
            return False

        except VaultError as e:
            logger.error(
                f"Failed to delete credentials from Vault",
                extra={"server_id": server_id, "error": str(e)},
            )
            raise

    def health_check(self) -> bool:
        """Check if Vault is accessible and authenticated.

        Returns:
            True if healthy, False otherwise
        """
        try:
            client = self._get_client()
            status = client.sys.read_health_status(method="GET")
            return status.get("sealed", True) is False
        except Exception:
            return False


# Global client instance
_vault_client: Optional[VaultClient] = None


def get_vault_client() -> VaultClient:
    """Get or create the global Vault client instance."""
    global _vault_client

    if _vault_client is None:
        _vault_client = VaultClient(
            vault_addr=f"https://vault.{settings.BASE_DOMAIN}",
            vault_token=os.environ.get("VAULT_TOKEN"),
            kubernetes_role="control-plane-api",
            mount_point="secret",
        )

    return _vault_client


async def shutdown_vault_client() -> None:
    """Cleanup Vault client resources."""
    global _vault_client
    _vault_client = None
