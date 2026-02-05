"""Grafana Provisioning Service (CAB-1089 Phase 5).

Provisions Grafana resources for each tenant at onboarding time:
- Folder (scoped to tenant)
- Team (auto-assigned via Keycloak OIDC team claim)
- Dashboard (tier-appropriate template)

Uses the Grafana HTTP API with a service account token.
"""
import json
import logging
from pathlib import Path

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Dashboard templates by tier (loaded once at import time)
_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "grafana-dashboard-templates"

TIER_TEMPLATE_MAP: dict[str, str] = {
    "demo": "tenant-basic.json",
    "platform": "tenant-basic.json",
    "business": "tenant-standard.json",
    "enterprise": "tenant-full.json",
}


class GrafanaProvisioningService:
    """Provisions Grafana folders, teams, and dashboards for tenants."""

    def __init__(self) -> None:
        self._base_url = settings.GRAFANA_API_URL.rstrip("/")
        self._token = settings.GRAFANA_SERVICE_ACCOUNT_TOKEN
        self._timeout = 15.0

    @property
    def _enabled(self) -> bool:
        return bool(self._base_url and self._token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Public API ──────────────────────────────────────────────

    async def provision_tenant(self, tenant_id: str, tenant_name: str, tier: str) -> dict:
        """Full provisioning flow for a new tenant.

        Returns dict with created resource IDs.
        """
        if not self._enabled:
            logger.info("Grafana provisioning disabled (no API URL or token)")
            return {"status": "skipped", "reason": "grafana_not_configured"}

        result: dict = {"tenant_id": tenant_id, "tier": tier}

        try:
            # 1. Create folder
            folder_uid = await self._create_folder(tenant_id, tenant_name)
            result["folder_uid"] = folder_uid

            # 2. Create team
            team_id = await self._create_team(tenant_id, tenant_name)
            result["team_id"] = team_id

            # 3. Assign folder permission to team
            if folder_uid and team_id:
                await self._set_folder_permission(folder_uid, team_id)

            # 4. Import dashboard from tier template
            dashboard_uid = await self._import_dashboard(tenant_id, tier, folder_uid)
            result["dashboard_uid"] = dashboard_uid

            result["status"] = "provisioned"
            logger.info(
                "Grafana provisioned for tenant %s (tier=%s, folder=%s, team=%s, dashboard=%s)",
                tenant_id, tier, folder_uid, team_id, dashboard_uid,
            )

        except Exception as e:
            logger.warning("Grafana provisioning failed for tenant %s: %s", tenant_id, e)
            result["status"] = "error"
            result["error"] = str(e)

        return result

    async def deprovision_tenant(self, tenant_id: str) -> None:
        """Remove Grafana resources for a deleted/archived tenant."""
        if not self._enabled:
            return

        try:
            folder_uid = f"tenant-{tenant_id}"
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Delete folder (cascades to dashboards inside it)
                resp = await client.delete(
                    f"{self._base_url}/api/folders/{folder_uid}",
                    headers=self._headers(),
                )
                if resp.status_code in (200, 404):
                    logger.info("Grafana folder deleted for tenant %s", tenant_id)
        except Exception as e:
            logger.warning("Grafana deprovision failed for tenant %s: %s", tenant_id, e)

    async def get_tenant_dashboard_url(self, tenant_id: str, tier: str) -> str:
        """Return the Grafana kiosk-mode URL for a tenant's dashboard."""
        dashboard_uid = f"tenant-{tenant_id}-overview"
        return (
            f"{settings.GRAFANA_URL}/d/{dashboard_uid}"
            f"?orgId=1&var-tenant_id={tenant_id}&kiosk"
        )

    # ── Private helpers ──────────────────────────────────────────

    async def _create_folder(self, tenant_id: str, tenant_name: str) -> str | None:
        """Create a Grafana folder for the tenant."""
        folder_uid = f"tenant-{tenant_id}"
        payload = {
            "uid": folder_uid,
            "title": f"Tenant: {tenant_name}",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/folders",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json().get("uid", folder_uid)
            if resp.status_code == 409:
                # Folder already exists
                logger.debug("Grafana folder already exists for tenant %s", tenant_id)
                return folder_uid
            logger.warning("Failed to create Grafana folder: %s %s", resp.status_code, resp.text)
            return folder_uid  # Return uid anyway for downstream use

    async def _create_team(self, tenant_id: str, tenant_name: str) -> int | None:
        """Create a Grafana team mapped to the tenant."""
        payload = {
            "name": f"tenant-{tenant_id}",
            "email": f"{tenant_id}@gostoa.dev",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/teams",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json().get("teamId")
            if resp.status_code == 409:
                # Team already exists — look it up
                search = await client.get(
                    f"{self._base_url}/api/teams/search",
                    headers=self._headers(),
                    params={"name": f"tenant-{tenant_id}"},
                )
                if search.status_code == 200:
                    teams = search.json().get("teams", [])
                    if teams:
                        return teams[0].get("id")
            logger.warning("Failed to create Grafana team: %s %s", resp.status_code, resp.text)
            return None

    async def _set_folder_permission(self, folder_uid: str, team_id: int) -> None:
        """Grant Editor permission on the folder to the tenant team."""
        payload = {
            "items": [
                {"teamId": team_id, "permission": 2},  # 2 = Editor
            ],
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/folders/{folder_uid}/permissions",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code not in (200, 409):
                logger.warning(
                    "Failed to set folder permissions: %s %s", resp.status_code, resp.text
                )

    async def _import_dashboard(
        self, tenant_id: str, tier: str, folder_uid: str | None
    ) -> str | None:
        """Import the tier-appropriate dashboard template into the tenant folder."""
        template_name = TIER_TEMPLATE_MAP.get(tier, "tenant-basic.json")
        template_path = _TEMPLATE_DIR / template_name

        if not template_path.exists():
            logger.warning("Dashboard template not found: %s", template_path)
            return None

        dashboard_json = json.loads(template_path.read_text())

        # Customize for this tenant
        dashboard_uid = f"tenant-{tenant_id}-overview"
        dashboard_json["uid"] = dashboard_uid
        dashboard_json["title"] = f"Tenant Overview — {tenant_id}"

        # Replace template variable defaults
        for tpl in dashboard_json.get("templating", {}).get("list", []):
            if tpl.get("name") == "tenant_id":
                tpl["current"] = {"text": tenant_id, "value": tenant_id}
                tpl["options"] = [{"text": tenant_id, "value": tenant_id, "selected": True}]

        payload = {
            "dashboard": dashboard_json,
            "folderUid": folder_uid or f"tenant-{tenant_id}",
            "overwrite": True,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/dashboards/db",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json().get("uid", dashboard_uid)
            logger.warning(
                "Failed to import dashboard: %s %s", resp.status_code, resp.text
            )
            return None


# Module-level singleton
grafana_provisioning_service = GrafanaProvisioningService()
