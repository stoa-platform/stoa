"""STOA Gateway adapter — implements GatewayAdapterInterface.

Calls the Rust stoa-gateway admin API at /admin/* to manage
API routes, policies, and health checks. Uses httpx.AsyncClient
for async HTTP communication.

The stoa-gateway stores routes and policies in-memory; the Control
Plane is the source of truth and re-syncs on gateway restart via
the sync engine's drift detection.
"""

import logging

import httpx

from ..gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from . import mappers

logger = logging.getLogger(__name__)

_NOT_SUPPORTED = "Not supported by STOA gateway"


class StoaGatewayAdapter(GatewayAdapterInterface):
    """STOA Gateway implementation of the Gateway Adapter.

    Communicates with the Rust stoa-gateway via its admin API
    (bearer-token authenticated). All methods are idempotent.
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)
        self._base_url = (config or {}).get("base_url", "http://localhost:8080")
        auth_config = (config or {}).get("auth_config", {})
        self._admin_token = auth_config.get("admin_token", "") if isinstance(auth_config, dict) else ""
        self._client: httpx.AsyncClient | None = None

    # --- Lifecycle ---

    async def health_check(self) -> AdapterResult:
        try:
            client = self._client or httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._auth_headers(),
                timeout=10.0,
            )
            resp = await client.get("/admin/health")
            if self._client is None:
                await client.aclose()

            if resp.status_code == 200:
                data = resp.json()
                return AdapterResult(success=True, data=data)
            return AdapterResult(
                success=False, error=f"Health check failed: HTTP {resp.status_code}"
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._auth_headers(),
            timeout=30.0,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # --- APIs ---

    async def sync_api(
        self, api_spec: dict, tenant_id: str, auth_token: str | None = None
    ) -> AdapterResult:
        try:
            payload = mappers.map_api_spec_to_stoa(api_spec, tenant_id)
            resp = await self._client.post("/admin/apis", json=payload)

            if resp.status_code in (200, 201):
                data = resp.json()
                return AdapterResult(
                    success=True,
                    resource_id=data.get("id", payload.get("id", "")),
                    data={"spec_hash": payload.get("spec_hash", "")},
                )
            return AdapterResult(
                success=False, error=f"sync_api failed: HTTP {resp.status_code} — {resp.text}"
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(
        self, api_id: str, auth_token: str | None = None
    ) -> AdapterResult:
        try:
            resp = await self._client.delete(f"/admin/apis/{api_id}")
            if resp.status_code in (200, 204):
                return AdapterResult(success=True, resource_id=api_id)
            if resp.status_code == 404:
                # Already deleted — idempotent
                return AdapterResult(success=True, resource_id=api_id)
            return AdapterResult(
                success=False, error=f"delete_api failed: HTTP {resp.status_code}"
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        try:
            resp = await self._client.get("/admin/apis")
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []

    # --- Policies ---

    async def upsert_policy(
        self, policy_spec: dict, auth_token: str | None = None
    ) -> AdapterResult:
        try:
            payload = mappers.map_policy_to_stoa(policy_spec)
            resp = await self._client.post("/admin/policies", json=payload)

            if resp.status_code in (200, 201):
                data = resp.json()
                return AdapterResult(
                    success=True,
                    resource_id=data.get("id", payload.get("id", "")),
                    data=data,
                )
            return AdapterResult(
                success=False,
                error=f"upsert_policy failed: HTTP {resp.status_code} — {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_policy(
        self, policy_id: str, auth_token: str | None = None
    ) -> AdapterResult:
        try:
            resp = await self._client.delete(f"/admin/policies/{policy_id}")
            if resp.status_code in (200, 204):
                return AdapterResult(success=True, resource_id=policy_id)
            if resp.status_code == 404:
                return AdapterResult(success=True, resource_id=policy_id)
            return AdapterResult(
                success=False, error=f"delete_policy failed: HTTP {resp.status_code}"
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        try:
            resp = await self._client.get("/admin/policies")
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []

    # --- Applications (not supported by stoa-gateway) ---

    async def provision_application(
        self, app_spec: dict, auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def deprovision_application(
        self, app_id: str, auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        return []

    # --- Auth / OIDC (not supported by stoa-gateway) ---

    async def upsert_auth_server(
        self, auth_spec: dict, auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def upsert_strategy(
        self, strategy_spec: dict, auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def upsert_scope(
        self, scope_spec: dict, auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    # --- Aliases (not supported by stoa-gateway) ---

    async def upsert_alias(
        self, alias_spec: dict, auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    # --- Configuration (not supported by stoa-gateway) ---

    async def apply_config(
        self, config_spec: dict, auth_token: str | None = None
    ) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    # --- Backup (not supported by stoa-gateway) ---

    async def export_archive(self, auth_token: str | None = None) -> bytes:
        return b""

    # --- Internal helpers ---

    def _auth_headers(self) -> dict:
        """Build auth headers for admin API requests."""
        headers = {}
        if self._admin_token:
            headers["Authorization"] = f"Bearer {self._admin_token}"
        return headers
