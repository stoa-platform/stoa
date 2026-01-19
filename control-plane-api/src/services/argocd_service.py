"""ArgoCD service for GitOps observability (CAB-654)

Provides access to Argo CD Application status for platform monitoring.
Uses OIDC authentication - forwards user's Keycloak token to ArgoCD.
"""
import logging
from typing import Optional, List
from datetime import datetime
import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class ArgoCDService:
    """Service for Argo CD operations and status monitoring.

    Uses OIDC authentication by forwarding the user's Keycloak token.
    ArgoCD is configured to accept tokens from the same Keycloak realm.
    """

    def __init__(self):
        self._base_url: str = settings.ARGOCD_URL.rstrip("/")

    @property
    def is_connected(self) -> bool:
        """Check if service is configured"""
        return bool(self._base_url)

    async def connect(self):
        """Initialize ArgoCD service (no-op, uses per-request auth)"""
        logger.info(f"ArgoCD service configured for {self._base_url} (OIDC auth)")

    async def disconnect(self):
        """Cleanup (no-op for OIDC mode)"""
        pass

    async def _request(self, auth_token: str, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request to ArgoCD with user's token."""
        async with httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v1",
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
            verify=settings.ARGOCD_VERIFY_SSL,
        ) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

    async def health_check(self, auth_token: str) -> bool:
        """Check if ArgoCD is healthy and reachable"""
        try:
            await self._request(auth_token, "GET", "/version")
            return True
        except Exception as e:
            logger.warning(f"ArgoCD health check failed: {e}")
            return False

    async def get_applications(self, auth_token: str, project: str = "") -> List[dict]:
        """
        List all applications, optionally filtered by project.

        Args:
            auth_token: User's OIDC token
            project: Optional project filter (e.g., "stoa")

        Returns:
            List of application objects
        """
        params = {}
        if project:
            params["project"] = project

        result = await self._request(auth_token, "GET", "/applications", params=params)
        return result.get("items", [])

    async def get_application(self, auth_token: str, name: str) -> dict:
        """
        Get application details by name.

        Args:
            auth_token: User's OIDC token
            name: Application name

        Returns:
            Application object with status
        """
        return await self._request(auth_token, "GET", f"/applications/{name}")

    async def get_application_sync_status(self, auth_token: str, name: str) -> dict:
        """
        Get sync status for an application.

        Args:
            auth_token: User's OIDC token
            name: Application name

        Returns:
            Sync status details
        """
        app = await self.get_application(auth_token, name)
        status = app.get("status", {})

        return {
            "name": name,
            "sync_status": status.get("sync", {}).get("status", "Unknown"),
            "health_status": status.get("health", {}).get("status", "Unknown"),
            "revision": status.get("sync", {}).get("revision", ""),
            "operation_state": status.get("operationState"),
            "conditions": status.get("conditions", []),
        }

    async def get_platform_status(self, auth_token: str, app_names: Optional[List[str]] = None) -> dict:
        """
        Get aggregated platform status for multiple applications.

        Args:
            auth_token: User's OIDC token
            app_names: List of application names to check.
                      If None, uses default STOA platform apps.

        Returns:
            Platform status summary
        """
        if app_names is None:
            app_names = settings.argocd_platform_apps_list

        components = []
        overall_healthy = True
        overall_synced = True

        for app_name in app_names:
            try:
                app = await self.get_application(auth_token, app_name)
                status = app.get("status", {})
                spec = app.get("spec", {})

                sync_status = status.get("sync", {}).get("status", "Unknown")
                health_status = status.get("health", {}).get("status", "Unknown")

                if health_status not in ["Healthy", "Progressing"]:
                    overall_healthy = False
                if sync_status != "Synced":
                    overall_synced = False

                op_state = status.get("operationState", {})
                last_sync = op_state.get("finishedAt") if op_state else None

                components.append({
                    "name": app_name,
                    "display_name": spec.get("destination", {}).get("namespace", app_name),
                    "sync_status": sync_status,
                    "health_status": health_status,
                    "revision": status.get("sync", {}).get("revision", "")[:8] if status.get("sync", {}).get("revision") else "",
                    "last_sync": last_sync,
                    "message": health_status if health_status != "Healthy" else None,
                })

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    components.append({
                        "name": app_name,
                        "display_name": app_name,
                        "sync_status": "NotFound",
                        "health_status": "Unknown",
                        "revision": "",
                        "last_sync": None,
                        "message": "Application not found",
                    })
                    overall_healthy = False
                elif e.response.status_code in (401, 403):
                    components.append({
                        "name": app_name,
                        "display_name": app_name,
                        "sync_status": "Error",
                        "health_status": "Unknown",
                        "revision": "",
                        "last_sync": None,
                        "message": "Access denied - check ArgoCD RBAC",
                    })
                    overall_healthy = False
                else:
                    raise
            except Exception as e:
                logger.warning(f"Failed to get status for {app_name}: {e}")
                components.append({
                    "name": app_name,
                    "display_name": app_name,
                    "sync_status": "Error",
                    "health_status": "Unknown",
                    "revision": "",
                    "last_sync": None,
                    "message": str(e),
                })
                overall_healthy = False

        if overall_healthy and overall_synced:
            overall_status = "healthy"
        elif not overall_healthy:
            overall_status = "degraded"
        else:
            overall_status = "syncing"

        return {
            "status": overall_status,
            "components": components,
            "checked_at": datetime.utcnow().isoformat() + "Z",
        }

    async def get_application_events(self, auth_token: str, app_name: str, limit: int = 20) -> List[dict]:
        """
        Get recent events for an application.

        Args:
            auth_token: User's OIDC token
            app_name: Application name
            limit: Maximum number of events to return

        Returns:
            List of event objects
        """
        app = await self.get_application(auth_token, app_name)
        history = app.get("status", {}).get("history", [])

        events = []
        for entry in history[-limit:]:
            revision = entry.get("revision", "")
            events.append({
                "id": entry.get("id"),
                "revision": revision[:8] if revision else "",
                "deployed_at": entry.get("deployedAt"),
                "source": entry.get("source", {}).get("repoURL", ""),
            })

        return list(reversed(events))

    async def sync_application(self, auth_token: str, name: str, revision: str = "HEAD", prune: bool = False) -> dict:
        """
        Trigger a sync for an application.

        Args:
            auth_token: User's OIDC token
            name: Application name
            revision: Git revision to sync to
            prune: Whether to prune resources no longer in Git

        Returns:
            Sync operation result
        """
        payload = {
            "revision": revision,
            "prune": prune,
            "dryRun": False,
        }

        logger.info(f"Triggering sync for application {name}", extra={
            "revision": revision,
            "prune": prune
        })

        return await self._request(auth_token, "POST", f"/applications/{name}/sync", json=payload)

    async def get_application_diff(self, auth_token: str, name: str) -> dict:
        """
        Get the diff between desired and live state for an application.

        Args:
            auth_token: User's OIDC token
            name: Application name

        Returns:
            Diff object with managed resources and their status
        """
        result = await self._request(auth_token, "GET", f"/applications/{name}/managed-resources")
        resources = result.get("items", [])

        diff_resources = []
        for resource in resources:
            if resource.get("diff") or resource.get("status") == "OutOfSync":
                diff_resources.append({
                    "name": resource.get("name"),
                    "namespace": resource.get("namespace"),
                    "kind": resource.get("kind"),
                    "group": resource.get("group"),
                    "status": resource.get("status"),
                    "health": resource.get("health", {}).get("status"),
                    "diff": resource.get("diff"),
                })

        return {
            "application": name,
            "total_resources": len(resources),
            "diff_count": len(diff_resources),
            "resources": diff_resources,
        }

    async def get_sync_summary(self, auth_token: str) -> dict:
        """
        Get aggregated sync summary for all platform applications.

        Args:
            auth_token: User's OIDC token

        Returns:
            Summary with counts and overall status
        """
        try:
            apps_status = await self.get_platform_status(auth_token)
            components = apps_status.get("components", [])

            synced = sum(1 for c in components if c["sync_status"] == "Synced")
            out_of_sync = sum(1 for c in components if c["sync_status"] == "OutOfSync")
            healthy = sum(1 for c in components if c["health_status"] == "Healthy")
            degraded = sum(1 for c in components if c["health_status"] in ("Degraded", "Missing", "Unknown"))

            return {
                "total_apps": len(components),
                "synced_count": synced,
                "out_of_sync_count": out_of_sync,
                "healthy_count": healthy,
                "degraded_count": degraded,
                "apps": components,
                "argocd_url": settings.ARGOCD_URL,
            }
        except Exception as e:
            logger.error(f"Failed to get sync summary: {e}")
            return {
                "total_apps": 0,
                "synced_count": 0,
                "out_of_sync_count": 0,
                "healthy_count": 0,
                "degraded_count": 0,
                "apps": [],
                "argocd_url": settings.ARGOCD_URL,
                "error": str(e),
            }


# Global instance
argocd_service = ArgoCDService()
