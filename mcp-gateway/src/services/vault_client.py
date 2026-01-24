"""HashiCorp Vault Client for Secure API Key Storage.

Provides secure storage and retrieval of API keys using HashiCorp Vault.
Uses Kubernetes authentication in cluster, token auth for development.

Reference: CAB-XXX - Secure API Key Management with Vault & 2FA
"""

import os
from functools import lru_cache
from typing import Any

import structlog
import hvac
from hvac.exceptions import VaultError, InvalidPath

from ..config import get_settings

logger = structlog.get_logger(__name__)


class VaultClient:
    """HashiCorp Vault client for API key storage.

    Stores API keys at: secret/data/subscriptions/{subscription_id}
    """

    def __init__(
        self,
        vault_addr: str,
        vault_token: str | None = None,
        kubernetes_role: str | None = None,
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
        self._client: hvac.Client | None = None
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
                logger.warning("Kubernetes auth failed, falling back to token", error=str(e))

        # Fall back to token auth (development)
        if self._vault_token:
            self._client.token = self._vault_token
            if self._client.is_authenticated():
                logger.info("Authenticated with Vault using token auth")
                return self._client

        raise VaultError("Failed to authenticate with Vault")

    async def store_api_key(
        self,
        subscription_id: str,
        api_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store an API key in Vault.

        Args:
            subscription_id: Unique subscription identifier
            api_key: The API key to store (plaintext)
            metadata: Optional metadata (user_id, tool_id, created_at)

        Returns:
            The Vault path where the key is stored
        """
        client = self._get_client()
        path = f"subscriptions/{subscription_id}"

        secret_data = {
            "api_key": api_key,
            **(metadata or {}),
        }

        try:
            client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=secret_data,
                mount_point=self.mount_point,
            )

            full_path = f"{self.mount_point}/data/{path}"
            logger.info(
                "API key stored in Vault",
                subscription_id=subscription_id,
                path=full_path,
            )
            return full_path

        except VaultError as e:
            logger.error(
                "Failed to store API key in Vault",
                subscription_id=subscription_id,
                error=str(e),
            )
            raise

    async def retrieve_api_key(self, subscription_id: str) -> str | None:
        """Retrieve an API key from Vault.

        Args:
            subscription_id: Unique subscription identifier

        Returns:
            The API key if found, None otherwise
        """
        client = self._get_client()
        path = f"subscriptions/{subscription_id}"

        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point,
            )

            if response and "data" in response and "data" in response["data"]:
                api_key = response["data"]["data"].get("api_key")
                logger.info(
                    "API key retrieved from Vault",
                    subscription_id=subscription_id,
                )
                return api_key

            return None

        except InvalidPath:
            logger.warning(
                "API key not found in Vault",
                subscription_id=subscription_id,
            )
            return None

        except VaultError as e:
            logger.error(
                "Failed to retrieve API key from Vault",
                subscription_id=subscription_id,
                error=str(e),
            )
            raise

    async def delete_api_key(self, subscription_id: str) -> bool:
        """Delete an API key from Vault.

        Args:
            subscription_id: Unique subscription identifier

        Returns:
            True if deleted, False if not found
        """
        client = self._get_client()
        path = f"subscriptions/{subscription_id}"

        try:
            # Permanently delete all versions
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point=self.mount_point,
            )

            logger.info(
                "API key deleted from Vault",
                subscription_id=subscription_id,
            )
            return True

        except InvalidPath:
            logger.warning(
                "API key not found for deletion",
                subscription_id=subscription_id,
            )
            return False

        except VaultError as e:
            logger.error(
                "Failed to delete API key from Vault",
                subscription_id=subscription_id,
                error=str(e),
            )
            raise

    async def rotate_api_key(
        self,
        subscription_id: str,
        new_api_key: str,
    ) -> str:
        """Rotate an API key (store new version).

        Args:
            subscription_id: Unique subscription identifier
            new_api_key: The new API key

        Returns:
            The Vault path where the key is stored
        """
        # Just update - Vault KV v2 keeps version history
        return await self.store_api_key(subscription_id, new_api_key)

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
_vault_client: VaultClient | None = None


def get_vault_client() -> VaultClient:
    """Get or create the global Vault client instance."""
    global _vault_client

    if _vault_client is None:
        settings = get_settings()
        _vault_client = VaultClient(
            vault_addr=f"https://vault.{settings.base_domain}",
            vault_token=os.environ.get("VAULT_TOKEN"),
            kubernetes_role="mcp-gateway",
            mount_point="secret",
        )

    return _vault_client


async def shutdown_vault_client() -> None:
    """Cleanup Vault client resources."""
    global _vault_client
    _vault_client = None
