"""ArgoCD service for GitOps observability (CAB-654)

Provides access to Argo CD Application status for platform monitoring.
"""
import logging
from typing import Optional, List
from datetime import datetime
import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class ArgoCDService:
    """Service for Argo CD operations and status monitoring"""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url: str = ""
        self._connected: bool = False

    @property
    def is_connected(self) -> bool:
        """Check if service is connected"""
        return self._connected and self._client is not None

    async def connect(self):
        """Initialize ArgoCD connection"""
        if not settings.ARGOCD_TOKEN:
            logger.warning("ArgoCD token not configured, service will be unavailable")
            return

        self._base_url = settings.ARGOCD_URL.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v1",
            headers={
                "Authorization": f"Bearer {settings.ARGOCD_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
            verify=settings.ARGOCD_VERIFY_SSL,
        )
        self._connected = True
        logger.info(f"Connected to ArgoCD at {self._base_url}")

    async def disconnect(self):
        """Close ArgoCD connection"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def health_check(self) -> bool:
        """Check if ArgoCD is healthy and reachable"""
        if not self.is_connected:
            return False
        try:
            # Use version endpoint as health check
            response = await self._client.get("/version")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"ArgoCD health check failed: {e}")
            return False

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request to ArgoCD"""
        if not self._client:
            raise RuntimeError("ArgoCD not connected")

        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def get_applications(self, project: str = "") -> List[dict]:
        """
        List all applications, optionally filtered by project.

        Args:
            project: Optional project filter (e.g., "stoa")

        Returns:
            List of application objects
        """
        params = {}
        if project:
            params["project"] = project

        result = await self._request("GET", "/applications", params=params)
        return result.get("items", [])

    async def get_application(self, name: str) -> dict:
        """
        Get application details by name.

        Args:
            name: Application name

        Returns:
            Application object with status
        """
        return await self._request("GET", f"/applications/{name}")

    async def get_application_sync_status(self, name: str) -> dict:
        """
        Get sync status for an application.

        Args:
            name: Application name

        Returns:
            Sync status details
        """
        app = await self.get_application(name)
        status = app.get("status", {})

        return {
            "name": name,
            "sync_status": status.get("sync", {}).get("status", "Unknown"),
            "health_status": status.get("health", {}).get("status", "Unknown"),
            "revision": status.get("sync", {}).get("revision", ""),
            "operation_state": status.get("operationState"),
            "conditions": status.get("conditions", []),
        }

    async def get_platform_status(self, app_names: Optional[List[str]] = None) -> dict:
        """
        Get aggregated platform status for multiple applications.

        Args:
            app_names: List of application names to check.
                      If None, uses default STOA platform apps.

        Returns:
            Platform status summary
        """
        if app_names is None:
            # Default STOA platform applications
            app_names = settings.argocd_platform_apps_list

        components = []
        overall_healthy = True
        overall_synced = True

        for app_name in app_names:
            try:
                app = await self.get_application(app_name)
                status = app.get("status", {})
                spec = app.get("spec", {})

                sync_status = status.get("sync", {}).get("status", "Unknown")
                health_status = status.get("health", {}).get("status", "Unknown")

                # Check health and sync
                if health_status not in ["Healthy", "Progressing"]:
                    overall_healthy = False
                if sync_status != "Synced":
                    overall_synced = False

                # Get operation info
                op_state = status.get("operationState", {})
                last_sync = None
                if op_state.get("finishedAt"):
                    last_sync = op_state.get("finishedAt")

                components.append({
                    "name": app_name,
                    "display_name": spec.get("destination", {}).get("namespace", app_name),
                    "sync_status": sync_status,
                    "health_status": health_status,
                    "revision": status.get("sync", {}).get("revision", "")[:8],
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

        # Determine overall status
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

    async def get_application_events(
        self,
        app_name: str,
        limit: int = 20
    ) -> List[dict]:
        """
        Get recent events for an application.

        Args:
            app_name: Application name
            limit: Maximum number of events to return

        Returns:
            List of event objects
        """
        # ArgoCD events are in the resource-tree or via K8s events
        # For now, we'll use the operation history
        app = await self.get_application(app_name)
        history = app.get("status", {}).get("history", [])

        events = []
        for entry in history[-limit:]:
            events.append({
                "id": entry.get("id"),
                "revision": entry.get("revision", "")[:8],
                "deployed_at": entry.get("deployedAt"),
                "source": entry.get("source", {}).get("repoURL", ""),
            })

        return list(reversed(events))  # Most recent first

    async def sync_application(self, name: str, revision: str = "HEAD", prune: bool = False) -> dict:
        """
        Trigger a sync for an application.

        Args:
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

        return await self._request(
            "POST",
            f"/applications/{name}/sync",
            json=payload
        )

    async def get_application_diff(self, name: str) -> dict:
        """
        Get the diff between desired and live state for an application.

        Args:
            name: Application name

        Returns:
            Diff object with managed resources and their status
        """
        # Get managed resources with their diff status
        result = await self._request("GET", f"/applications/{name}/managed-resources")
        resources = result.get("items", [])

        # Filter to only show resources with differences
        diff_resources = []
        for resource in resources:
            # Check if resource has diff
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

    async def get_sync_summary(self) -> dict:
        """
        Get aggregated sync summary for all platform applications.

        Returns:
            Summary with counts and overall status
        """
        try:
            apps_status = await self.get_platform_status()
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
