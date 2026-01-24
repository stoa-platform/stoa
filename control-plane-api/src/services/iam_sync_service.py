"""IAM Sync Service - Synchronizes GitOps tenant/user configs with Keycloak

This service ensures consistency between GitOps repository and Keycloak:
- Tenant groups
- User roles and permissions
- Application clients (OAuth2)
"""
import logging
from typing import Optional
from datetime import datetime

import yaml

from .git_service import git_service
from .keycloak_service import keycloak_service
from .kafka_service import kafka_service, Topics

logger = logging.getLogger(__name__)


class IAMSyncService:
    """
    Synchronizes IAM configuration between GitOps and Keycloak.

    This service handles:
    1. Tenant group creation/deletion in Keycloak
    2. User role assignments based on GitOps config
    3. Application OAuth2 client management
    4. Reconciliation between GitOps state and Keycloak state
    """

    def __init__(self):
        self._last_sync: Optional[datetime] = None

    async def sync_tenant(self, tenant_id: str) -> dict:
        """
        Sync a tenant's IAM configuration from GitOps to Keycloak.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Sync result with actions taken
        """
        result = {
            "tenant_id": tenant_id,
            "synced_at": datetime.utcnow().isoformat() + "Z",
            "actions": [],
            "errors": [],
        }

        try:
            # Get tenant config from GitOps
            tenant_data = await git_service.get_tenant(tenant_id)
            if not tenant_data:
                result["errors"].append(f"Tenant {tenant_id} not found in GitOps")
                return result

            # Ensure tenant group exists in Keycloak
            try:
                await keycloak_service.setup_tenant_group(
                    tenant_id,
                    tenant_data.get("display_name", tenant_id)
                )
                result["actions"].append(f"Ensured group exists: {tenant_id}")
            except Exception as e:
                logger.warning(f"Group setup failed (may already exist): {e}")

            # Get users config from GitOps (if exists)
            users_config = await self._get_tenant_users_config(tenant_id)
            if users_config:
                for user_config in users_config.get("users", []):
                    try:
                        await self._sync_user(tenant_id, user_config)
                        result["actions"].append(f"Synced user: {user_config.get('email')}")
                    except Exception as e:
                        result["errors"].append(f"Failed to sync user {user_config.get('email')}: {e}")

            # Sync applications (OAuth2 clients)
            # TODO: Implement application sync

            logger.info(f"Synced tenant {tenant_id}: {len(result['actions'])} actions")
            return result

        except Exception as e:
            logger.error(f"Failed to sync tenant {tenant_id}: {e}")
            result["errors"].append(str(e))
            return result

    async def _get_tenant_users_config(self, tenant_id: str) -> Optional[dict]:
        """Get users configuration from GitOps for a tenant."""
        try:
            content = await git_service.get_file(
                f"tenants/{tenant_id}/iam/users.yaml"
            )
            if content:
                return yaml.safe_load(content)
        except Exception:
            pass
        return None

    async def _sync_user(self, tenant_id: str, user_config: dict) -> bool:
        """
        Sync a single user configuration.

        Args:
            tenant_id: Tenant ID
            user_config: User configuration from GitOps

        Returns:
            True if sync successful
        """
        email = user_config.get("email")
        if not email:
            return False

        # Check if user exists in Keycloak
        users = await keycloak_service.get_users(tenant_id)
        existing_user = next(
            (u for u in users if u.get("email") == email),
            None
        )

        roles = user_config.get("roles", ["viewer"])

        if existing_user:
            # Update existing user roles
            user_id = existing_user["id"]
            for role in roles:
                try:
                    await keycloak_service.assign_role(user_id, role)
                except Exception as e:
                    logger.warning(f"Failed to assign role {role} to {email}: {e}")
        else:
            # Create new user
            try:
                await keycloak_service.create_user(
                    username=user_config.get("username", email.split("@")[0]),
                    email=email,
                    first_name=user_config.get("first_name", ""),
                    last_name=user_config.get("last_name", ""),
                    tenant_id=tenant_id,
                    roles=roles,
                )
            except Exception as e:
                logger.error(f"Failed to create user {email}: {e}")
                raise

        return True

    async def sync_all_tenants(self) -> dict:
        """
        Sync all tenants from GitOps to Keycloak.

        Returns:
            Summary of sync operations
        """
        result = {
            "synced_at": datetime.utcnow().isoformat() + "Z",
            "tenants": [],
            "total_actions": 0,
            "total_errors": 0,
        }

        try:
            # List all tenants from GitOps
            if not git_service._project:
                result["errors"] = ["GitLab not connected"]
                return result

            tree = git_service._project.repository_tree(path="tenants", ref="main")

            for item in tree:
                if item["type"] == "tree":
                    tenant_id = item["name"]
                    tenant_result = await self.sync_tenant(tenant_id)
                    result["tenants"].append(tenant_result)
                    result["total_actions"] += len(tenant_result.get("actions", []))
                    result["total_errors"] += len(tenant_result.get("errors", []))

            self._last_sync = datetime.utcnow()
            logger.info(f"Full IAM sync completed: {len(result['tenants'])} tenants")

        except Exception as e:
            logger.error(f"Full IAM sync failed: {e}")
            result["errors"] = [str(e)]

        return result

    async def reconcile_tenant(self, tenant_id: str) -> dict:
        """
        Reconcile Keycloak state with GitOps for a tenant.

        This compares the current Keycloak state with GitOps and
        reports any drift.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Reconciliation report
        """
        report = {
            "tenant_id": tenant_id,
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "in_sync": True,
            "drift": [],
        }

        try:
            # Get GitOps config
            users_config = await self._get_tenant_users_config(tenant_id)
            gitops_users = {u["email"]: u for u in users_config.get("users", [])} if users_config else {}

            # Get Keycloak state
            kc_users = await keycloak_service.get_users(tenant_id)
            kc_user_emails = {u["email"] for u in kc_users if u.get("email")}

            # Find drift
            gitops_emails = set(gitops_users.keys())

            # Users in GitOps but not in Keycloak
            missing_in_kc = gitops_emails - kc_user_emails
            for email in missing_in_kc:
                report["drift"].append({
                    "type": "missing_user",
                    "email": email,
                    "message": f"User {email} defined in GitOps but not in Keycloak",
                })
                report["in_sync"] = False

            # Users in Keycloak but not in GitOps
            extra_in_kc = kc_user_emails - gitops_emails
            for email in extra_in_kc:
                report["drift"].append({
                    "type": "extra_user",
                    "email": email,
                    "message": f"User {email} exists in Keycloak but not in GitOps",
                })
                report["in_sync"] = False

            # TODO: Check role assignments

            logger.info(f"Reconciliation for {tenant_id}: in_sync={report['in_sync']}")
            return report

        except Exception as e:
            logger.error(f"Reconciliation failed for {tenant_id}: {e}")
            report["error"] = str(e)
            return report

    async def handle_tenant_event(self, event: dict) -> None:
        """
        Handle tenant lifecycle events from Kafka.

        Args:
            event: Kafka event payload
        """
        event_type = event.get("type")
        tenant_id = event.get("tenant_id")

        if not tenant_id:
            logger.warning("Tenant event missing tenant_id")
            return

        if event_type == "tenant-created":
            # Sync new tenant to Keycloak
            await self.sync_tenant(tenant_id)

        elif event_type == "tenant-deleted":
            # Clean up Keycloak resources
            # TODO: Implement cleanup (delete group, users, clients)
            pass

        elif event_type == "user-added":
            # Sync user to Keycloak
            user_data = event.get("payload", {})
            await self._sync_user(tenant_id, user_data)

        elif event_type == "user-removed":
            # Remove user from Keycloak (or just from tenant)
            user_email = event.get("payload", {}).get("email")
            if user_email:
                users = await keycloak_service.get_users(tenant_id)
                user = next((u for u in users if u.get("email") == user_email), None)
                if user:
                    # Remove from tenant group (don't delete user)
                    # TODO: Implement group removal
                    pass

    async def create_application_client(
        self,
        tenant_id: str,
        app_name: str,
        display_name: str,
        redirect_uris: list[str],
    ) -> dict:
        """
        Create OAuth2 client for an application.

        Args:
            tenant_id: Tenant ID
            app_name: Application name
            display_name: Display name
            redirect_uris: OAuth2 redirect URIs

        Returns:
            Client credentials
        """
        try:
            client = await keycloak_service.create_client(
                tenant_id=tenant_id,
                name=app_name,
                display_name=display_name,
                redirect_uris=redirect_uris,
            )

            # Emit event
            await kafka_service.publish(
                topic=Topics.APP_EVENTS,
                event_type="app-client-created",
                tenant_id=tenant_id,
                payload={
                    "app_name": app_name,
                    "client_id": client["client_id"],
                },
                user_id=None,
            )

            logger.info(f"Created OAuth2 client for {tenant_id}/{app_name}")
            return client

        except Exception as e:
            logger.error(f"Failed to create client for {app_name}: {e}")
            raise

    async def rotate_client_secret(self, tenant_id: str, app_name: str) -> str:
        """
        Rotate OAuth2 client secret.

        Args:
            tenant_id: Tenant ID
            app_name: Application name

        Returns:
            New client secret
        """
        client_id = f"{tenant_id}-{app_name}"

        try:
            client = await keycloak_service.get_client(client_id)
            if not client:
                raise ValueError(f"Client {client_id} not found")

            new_secret = await keycloak_service.regenerate_client_secret(client["id"])

            # Emit event
            await kafka_service.publish(
                topic=Topics.APP_EVENTS,
                event_type="app-secret-rotated",
                tenant_id=tenant_id,
                payload={
                    "app_name": app_name,
                    "client_id": client_id,
                },
                user_id=None,
            )

            logger.info(f"Rotated secret for client {client_id}")
            return new_secret

        except Exception as e:
            logger.error(f"Failed to rotate secret for {client_id}: {e}")
            raise


# Global instance
iam_sync_service = IAMSyncService()
