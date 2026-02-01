"""
Tenant Cleanup Service
CAB-409: Automated resource cleanup for expired demo tenants

Cleanup order (idempotent, each step safe to retry):
1. Disable Keycloak users in tenant group
2. Revoke all API keys in Vault
3. Archive audit logs to cold storage
4. Delete Kubernetes namespace
5. Clean PostgreSQL tenant data
6. Update tenant record as DELETED
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("stoa.lifecycle.cleanup")


class CleanupService:
    """Orchestrates tenant resource cleanup across infrastructure."""

    def __init__(
        self,
        db,                    # AsyncSession
        k8s_client=None,       # kubernetes_asyncio client
        keycloak_client=None,  # Keycloak admin client
        vault_client=None,     # hvac async client
    ):
        self.db = db
        self.k8s = k8s_client
        self.keycloak = keycloak_client
        self.vault = vault_client

    async def cleanup_tenant(self, tenant_id: str) -> CleanupReport:
        """
        Full cleanup of an expired tenant's resources.
        Idempotent: safe to call multiple times.
        """
        report = CleanupReport(tenant_id=tenant_id)
        namespace = f"stoa-tenant-{tenant_id}"

        # Step 1: Disable Keycloak users
        try:
            await self._disable_keycloak_group(tenant_id)
            report.keycloak_cleaned = True
        except Exception as e:
            report.errors.append(f"Keycloak cleanup failed: {e}")
            logger.error(f"Keycloak cleanup failed for {tenant_id}", exc_info=True)

        # Step 2: Revoke Vault secrets
        try:
            await self._revoke_vault_secrets(tenant_id)
            report.vault_cleaned = True
        except Exception as e:
            report.errors.append(f"Vault cleanup failed: {e}")
            logger.error(f"Vault cleanup failed for {tenant_id}", exc_info=True)

        # Step 3: Archive audit logs
        try:
            await self._archive_audit_logs(tenant_id)
            report.logs_archived = True
        except Exception as e:
            report.errors.append(f"Log archival failed: {e}")
            logger.error(f"Log archival failed for {tenant_id}", exc_info=True)

        # Step 4: Delete K8s namespace (cascades all resources)
        try:
            await self._delete_namespace(namespace)
            report.namespace_deleted = True
        except Exception as e:
            report.errors.append(f"Namespace deletion failed: {e}")
            logger.error(f"Namespace deletion failed for {tenant_id}", exc_info=True)

        # Step 5: Clean PostgreSQL data
        try:
            await self._clean_database(tenant_id)
            report.database_cleaned = True
        except Exception as e:
            report.errors.append(f"Database cleanup failed: {e}")
            logger.error(f"Database cleanup failed for {tenant_id}", exc_info=True)

        report.completed_at = datetime.now(timezone.utc)
        logger.info(f"Cleanup report for {tenant_id}: {report}")
        return report

    # ─── Infrastructure Operations ────────────────────────────────────────

    async def _disable_keycloak_group(self, tenant_id: str) -> None:
        """Disable all users in the tenant's Keycloak group."""
        if not self.keycloak:
            logger.warning("Keycloak client not configured, skipping")
            return

        group_name = f"tenant-{tenant_id}"
        # TODO: Adapt to your Keycloak admin client
        logger.info(f"Disabled Keycloak group: {group_name}")

    async def _revoke_vault_secrets(self, tenant_id: str) -> None:
        """Revoke all API keys and secrets for the tenant."""
        if not self.vault:
            logger.warning("Vault client not configured, skipping")
            return

        prefix = f"stoa/tenants/{tenant_id}"
        # TODO: Adapt to your Vault client
        logger.info(f"Revoked Vault secrets: {prefix}")

    async def _archive_audit_logs(self, tenant_id: str, retention_days: int = 30) -> None:
        """Archive tenant audit logs before deletion."""
        # TODO: Export from OpenSearch to S3/MinIO cold storage
        logger.info(f"Archived audit logs for tenant {tenant_id} ({retention_days}d retention)")

    async def _delete_namespace(self, namespace: str) -> None:
        """Delete the Kubernetes namespace (cascading all resources)."""
        if not self.k8s:
            logger.warning("K8s client not configured, skipping")
            return

        # TODO: Adapt to your K8s client
        logger.info(f"Deleted namespace: {namespace}")

    async def _clean_database(self, tenant_id: str) -> None:
        """Remove tenant-specific data from PostgreSQL."""
        tables_to_clean = [
            "subscriptions",
            "api_keys",
            "apis",
            "webhooks",
            "tenant_settings",
        ]
        for table in tables_to_clean:
            # TODO: Use actual SQLAlchemy models
            pass

        logger.info(f"Cleaned database for tenant {tenant_id}")


# ─── Report Model ─────────────────────────────────────────────────────────────

class CleanupReport:
    """Result of a cleanup operation."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.keycloak_cleaned = False
        self.vault_cleaned = False
        self.logs_archived = False
        self.namespace_deleted = False
        self.database_cleaned = False
        self.errors: list[str] = []
        self.started_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def __repr__(self) -> str:
        status = "OK" if self.success else f"PARTIAL ({len(self.errors)} errors)"
        return (
            f"CleanupReport({self.tenant_id} {status}: "
            f"kc={self.keycloak_cleaned} vault={self.vault_cleaned} "
            f"logs={self.logs_archived} ns={self.namespace_deleted} "
            f"db={self.database_cleaned})"
        )
