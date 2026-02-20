"""Kafka quota management service for multi-tenant noisy neighbor prevention"""

import logging
from dataclasses import dataclass
from enum import StrEnum

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class TenantTier(StrEnum):
    """Tenant subscription tier"""

    STANDARD = "standard"
    PREMIUM = "premium"


@dataclass
class QuotaPolicy:
    """Kafka quota policy configuration"""

    producer_byte_rate: int  # bytes/sec
    consumer_byte_rate: int  # bytes/sec
    request_percentage: int  # CPU % (100 = 1 core)


# Quota tiers (aligned with SLA tiers)
QUOTA_POLICIES = {
    TenantTier.STANDARD: QuotaPolicy(
        producer_byte_rate=10 * 1024 * 1024,  # 10 MB/s
        consumer_byte_rate=20 * 1024 * 1024,  # 20 MB/s
        request_percentage=25,  # 25% CPU
    ),
    TenantTier.PREMIUM: QuotaPolicy(
        producer_byte_rate=50 * 1024 * 1024,  # 50 MB/s
        consumer_byte_rate=100 * 1024 * 1024,  # 100 MB/s
        request_percentage=50,  # 50% CPU
    ),
}


class KafkaQuotaService:
    """Service for managing Kafka client quotas via Redpanda Admin API"""

    def __init__(self, admin_url: str | None = None):
        """
        Initialize quota service.

        Args:
            admin_url: Redpanda Admin API URL (defaults to settings.KAFKA_ADMIN_URL)
        """
        self.admin_url = admin_url or getattr(settings, "KAFKA_ADMIN_URL", "http://redpanda.stoa-system.svc.cluster.local:9644")

    def _client_id_for_tenant(self, tenant_id: str, tier: TenantTier) -> str:
        """
        Generate client ID prefix for a tenant.

        Args:
            tenant_id: Tenant identifier
            tier: Tenant subscription tier

        Returns:
            Client ID prefix (e.g., "tenant-premium-abc123")
        """
        return f"tenant-{tier.value}-{tenant_id}"

    async def apply_quota(self, tenant_id: str, tier: TenantTier) -> dict:
        """
        Apply quota policy to a tenant.

        Args:
            tenant_id: Tenant identifier
            tier: Subscription tier (standard or premium)

        Returns:
            Response from Redpanda Admin API

        Raises:
            httpx.HTTPError: If quota creation fails
        """
        if not settings.KAFKA_ENABLED:
            logger.info(f"Kafka disabled — skipping quota for {tenant_id}")
            return {"success": False, "reason": "kafka_disabled"}

        policy = QUOTA_POLICIES[tier]
        client_id = self._client_id_for_tenant(tenant_id, tier)

        quota_payload = {
            "entity_type": "client-id",
            "entity_name": client_id,
            "values": [
                {"key": "producer_byte_rate", "value": policy.producer_byte_rate},
                {"key": "consumer_byte_rate", "value": policy.consumer_byte_rate},
                {"key": "request_percentage", "value": policy.request_percentage},
            ],
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.admin_url}/v1/kafka_quotas",
                    json=quota_payload,
                )
                response.raise_for_status()
                logger.info(f"Applied {tier.value} quota to tenant {tenant_id} (client-id: {client_id})")
                return {"success": True, "client_id": client_id, "tier": tier.value}
            except httpx.HTTPError as e:
                logger.error(f"Failed to apply quota for {tenant_id}: {e}")
                raise

    async def remove_quota(self, tenant_id: str, tier: TenantTier) -> dict:
        """
        Remove quota policy from a tenant.

        Args:
            tenant_id: Tenant identifier
            tier: Subscription tier

        Returns:
            Response from Redpanda Admin API

        Raises:
            httpx.HTTPError: If quota deletion fails
        """
        if not settings.KAFKA_ENABLED:
            logger.info(f"Kafka disabled — skipping quota removal for {tenant_id}")
            return {"success": False, "reason": "kafka_disabled"}

        client_id = self._client_id_for_tenant(tenant_id, tier)

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.delete(
                    f"{self.admin_url}/v1/kafka_quotas",
                    params={"entity_type": "client-id", "entity_name": client_id},
                )
                response.raise_for_status()
                logger.info(f"Removed quota for tenant {tenant_id} (client-id: {client_id})")
                return {"success": True, "client_id": client_id}
            except httpx.HTTPError as e:
                logger.error(f"Failed to remove quota for {tenant_id}: {e}")
                raise

    async def list_quotas(self) -> list[dict]:
        """
        List all active quota policies.

        Returns:
            List of quota configurations

        Raises:
            httpx.HTTPError: If listing fails
        """
        if not settings.KAFKA_ENABLED:
            return []

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{self.admin_url}/v1/kafka_quotas")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to list quotas: {e}")
                raise

    async def health_check(self) -> bool:
        """
        Check if Redpanda Admin API is reachable.

        Returns:
            True if healthy, False otherwise
        """
        if not settings.KAFKA_ENABLED:
            return False

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self.admin_url}/v1/status/ready")
                return response.status_code == 200
            except Exception as e:
                logger.warning(f"Kafka Admin API health check failed: {e}")
                return False


# Global instance
quota_service = KafkaQuotaService()
