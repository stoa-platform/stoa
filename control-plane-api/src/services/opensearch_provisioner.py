"""OpenSearch Provisioner — Event-driven tenant role management (CAB-1685).

Creates and deletes OpenSearch security roles + role mappings when tenants
are provisioned or deprovisioned. Uses the OpenSearch Security REST API
to manage DLS/FLS roles dynamically.

RBAC mapping (STOA role → OpenSearch role):
  cpi-admin    → stoa_gw_admin (all indices, no DLS)
  tenant-admin → stoa_gw_tenant_{id} (DLS on tenant_id)
  devops       → stoa_gw_tenant_{id} (DLS on tenant_id)
  viewer       → stoa_gw_viewer_{id} (DLS + FLS, no PII)

ISM policy assignment (tenant tier → policy):
  free         → gateway-logs-free (7d, default via ism_template)
  pro          → gateway-logs-pro (90d, explicit assignment)
  enterprise   → gateway-logs-enterprise (365d, explicit assignment)

See CAB-1684 for infra templates and CAB-1681 for architectural context.
"""

import json
import logging

logger = logging.getLogger("stoa.opensearch.provisioner")

# PII fields excluded from viewer role via FLS
PII_FIELDS = ["request_body", "response_body", "auth_token"]

# Tier → ISM policy mapping
TIER_ISM_POLICIES = {
    "free": "gateway-logs-free",
    "pro": "gateway-logs-pro",
    "enterprise": "gateway-logs-enterprise",
}


class OpenSearchProvisioner:
    """Manages OpenSearch security roles for tenant lifecycle events."""

    def __init__(self, os_client=None):
        self._client = os_client

    def set_client(self, client) -> None:
        self._client = client

    async def provision_tenant(self, tenant_id: str, tier: str = "free") -> dict:
        """Create OpenSearch roles and role mappings for a new tenant.

        Returns a dict with created role names and any errors.
        """
        if not self._client:
            logger.warning("No OpenSearch client — skipping tenant provisioning for %s", tenant_id)
            return {"status": "skipped", "reason": "no_client"}

        safe_id = tenant_id.replace("-", "_")
        results: dict = {"tenant_id": tenant_id, "roles_created": [], "errors": []}

        # DLS filter: tenant's own docs + shared "platform" docs (anonymous/system requests)
        tenant_dls = json.dumps({
            "bool": {
                "should": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"tenant_id": "platform"}},
                ]
            }
        })

        # 1. Create tenant-scoped reader role (DLS, no FLS)
        reader_role = f"stoa_gw_tenant_{safe_id}"
        try:
            await self._create_role(
                role_name=reader_role,
                index_patterns=["stoa-gw-*", "audit*"],
                dls=tenant_dls,
                fls=None,
                allowed_actions=["read", "search"],
            )
            results["roles_created"].append(reader_role)
        except Exception as e:
            logger.error("Failed to create reader role %s: %s", reader_role, e)
            results["errors"].append({"role": reader_role, "error": str(e)})

        # 2. Create viewer role (DLS + FLS, excludes PII)
        viewer_role = f"stoa_gw_viewer_{safe_id}"
        try:
            await self._create_role(
                role_name=viewer_role,
                index_patterns=["stoa-gw-*", "audit*"],
                dls=tenant_dls,
                fls=[f"~{field}" for field in PII_FIELDS],
                allowed_actions=["read", "search"],
            )
            results["roles_created"].append(viewer_role)
        except Exception as e:
            logger.error("Failed to create viewer role %s: %s", viewer_role, e)
            results["errors"].append({"role": viewer_role, "error": str(e)})

        # 3. Create role mappings (empty initially — users added via KC sync)
        for role_name in [reader_role, viewer_role]:
            try:
                await self._create_role_mapping(role_name=role_name, users=[], backend_roles=[])
            except Exception as e:
                logger.error("Failed to create role mapping for %s: %s", role_name, e)
                results["errors"].append({"role_mapping": role_name, "error": str(e)})

        # 4. Assign tier-specific ISM policy (pro/enterprise only; free uses default ism_template)
        if tier in ("pro", "enterprise"):
            try:
                await self._assign_ism_policy(tenant_id, tier)
                results["ism_policy"] = TIER_ISM_POLICIES[tier]
            except Exception as e:
                logger.error("Failed to assign ISM policy for %s: %s", tenant_id, e)
                results["errors"].append({"ism_policy": tier, "error": str(e)})

        status = "ok" if not results["errors"] else "partial"
        results["status"] = status
        logger.info(
            "Provisioned OS roles for tenant %s: %d roles, %d errors",
            tenant_id,
            len(results["roles_created"]),
            len(results["errors"]),
        )
        return results

    async def deprovision_tenant(self, tenant_id: str) -> dict:
        """Delete OpenSearch roles and role mappings for a removed tenant."""
        if not self._client:
            logger.warning("No OpenSearch client — skipping tenant deprovisioning for %s", tenant_id)
            return {"status": "skipped", "reason": "no_client"}

        safe_id = tenant_id.replace("-", "_")
        roles = [f"stoa_gw_tenant_{safe_id}", f"stoa_gw_viewer_{safe_id}"]
        results: dict = {"tenant_id": tenant_id, "roles_deleted": [], "errors": []}

        for role_name in roles:
            # Delete role mapping first
            try:
                await self._delete_role_mapping(role_name)
            except Exception as e:
                logger.warning("Failed to delete role mapping %s: %s", role_name, e)

            # Delete role
            try:
                await self._delete_role(role_name)
                results["roles_deleted"].append(role_name)
            except Exception as e:
                logger.error("Failed to delete role %s: %s", role_name, e)
                results["errors"].append({"role": role_name, "error": str(e)})

        status = "ok" if not results["errors"] else "partial"
        results["status"] = status
        logger.info(
            "Deprovisioned OS roles for tenant %s: %d deleted, %d errors",
            tenant_id,
            len(results["roles_deleted"]),
            len(results["errors"]),
        )
        return results

    async def update_role_mapping(self, tenant_id: str, role: str, users: list[str]) -> None:
        """Update the role mapping for a tenant role with the given user list.

        Called when tenant membership changes (user added/removed from tenant).
        `role` is the STOA role: 'tenant-admin', 'devops', or 'viewer'.
        """
        if not self._client:
            return

        safe_id = tenant_id.replace("-", "_")
        os_role = f"stoa_gw_viewer_{safe_id}" if role == "viewer" else f"stoa_gw_tenant_{safe_id}"

        try:
            await self._create_role_mapping(role_name=os_role, users=users, backend_roles=[])
            logger.info("Updated role mapping %s with %d users", os_role, len(users))
        except Exception as e:
            logger.error("Failed to update role mapping %s: %s", os_role, e)
            raise

    async def update_tier(self, tenant_id: str, new_tier: str) -> None:
        """Update ISM policy for a tenant when their tier changes."""
        if not self._client:
            return

        if new_tier not in TIER_ISM_POLICIES:
            logger.warning("Unknown tier %s for tenant %s", new_tier, tenant_id)
            return

        try:
            await self._assign_ism_policy(tenant_id, new_tier)
            logger.info("Updated ISM policy for tenant %s to %s", tenant_id, new_tier)
        except Exception as e:
            logger.error("Failed to update ISM policy for %s: %s", tenant_id, e)
            raise

    # --- Internal helpers ---

    async def _create_role(
        self,
        role_name: str,
        index_patterns: list[str],
        dls: str | None,
        fls: list[str] | None,
        allowed_actions: list[str],
    ) -> None:
        """Create or update an OpenSearch security role via REST API."""
        index_perm: dict = {
            "index_patterns": index_patterns,
            "allowed_actions": allowed_actions,
        }
        if dls:
            index_perm["dls"] = dls
        if fls:
            index_perm["fls"] = fls

        body = {
            "cluster_permissions": ["cluster_composite_ops_ro"],
            "index_permissions": [
                index_perm,
                {
                    "index_patterns": [".kibana*", ".opensearch_dashboards*"],
                    "allowed_actions": ["read", "write", "create_index"],
                },
            ],
        }

        await self._client.transport.perform_request(
            "PUT",
            f"/_plugins/_security/api/roles/{role_name}",
            body=body,
        )
        logger.debug("Created/updated role: %s", role_name)

    async def _delete_role(self, role_name: str) -> None:
        """Delete an OpenSearch security role."""
        await self._client.transport.perform_request(
            "DELETE",
            f"/_plugins/_security/api/roles/{role_name}",
        )
        logger.debug("Deleted role: %s", role_name)

    async def _create_role_mapping(self, role_name: str, users: list[str], backend_roles: list[str]) -> None:
        """Create or update an OpenSearch role mapping."""
        body = {
            "users": users,
            "backend_roles": backend_roles,
        }
        await self._client.transport.perform_request(
            "PUT",
            f"/_plugins/_security/api/rolesmapping/{role_name}",
            body=body,
        )
        logger.debug("Created/updated role mapping: %s", role_name)

    async def _delete_role_mapping(self, role_name: str) -> None:
        """Delete an OpenSearch role mapping."""
        await self._client.transport.perform_request(
            "DELETE",
            f"/_plugins/_security/api/rolesmapping/{role_name}",
        )
        logger.debug("Deleted role mapping: %s", role_name)

    async def _assign_ism_policy(self, tenant_id: str, tier: str) -> None:
        """Assign a tier-specific ISM policy to existing tenant indices."""
        policy_id = TIER_ISM_POLICIES.get(tier)
        if not policy_id:
            return

        # Match all indices for this tenant across all gateway types
        index_pattern = f"stoa-gw-*-{tenant_id}-*"

        body = {"policy_id": policy_id}
        try:
            await self._client.transport.perform_request(
                "POST",
                f"/_plugins/_ism/add/{index_pattern}",
                body=body,
            )
            logger.debug("Assigned ISM policy %s to %s", policy_id, index_pattern)
        except Exception as e:
            # No indices yet is not an error — policy will apply when indices are created
            if "index_not_found" in str(e).lower():
                logger.debug("No indices yet for %s — ISM policy will apply on creation", index_pattern)
            else:
                raise


# Global instance
opensearch_provisioner = OpenSearchProvisioner()
