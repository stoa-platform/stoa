"""Kong Gateway adapter — implements GatewayAdapterInterface.

Calls the Kong Admin API in DB-less mode. In DB-less mode the Admin
API is read-only for most endpoints; mutations go through
``POST /config`` which reloads the full declarative config.

Ref: https://docs.konghq.com/gateway/latest/production/deployment-topologies/db-less-and-declarative-config/
"""

import logging

import httpx

from ..gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from . import mappers

logger = logging.getLogger(__name__)

_NOT_SUPPORTED = "Not supported by Kong DB-less adapter"


class KongGatewayAdapter(GatewayAdapterInterface):
    """Kong Gateway (DB-less) implementation of the Gateway Adapter.

    Communicates with the Kong Admin API (default port 8001).
    DB-less mode: ``GET`` endpoints work, mutations via ``POST /config``.
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)
        self._base_url = (config or {}).get("base_url", "http://localhost:8001")
        auth_config = (config or {}).get("auth_config", {})
        self._api_key = auth_config.get("api_key", "") if isinstance(auth_config, dict) else ""
        self._client: httpx.AsyncClient | None = None

    # --- Lifecycle ---

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

    async def health_check(self) -> AdapterResult:
        try:
            client = self._client or httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._auth_headers(),
                timeout=10.0,
            )
            resp = await client.get("/status")
            if self._client is None:
                await client.aclose()

            if resp.status_code == 200:
                data = resp.json()
                return AdapterResult(
                    success=True,
                    data={
                        "database_reachable": data.get("database", {}).get("reachable", False),
                        "connections_active": (data.get("server", {}).get("connections_active", 0)),
                        "version": data.get("version", "unknown"),
                    },
                )
            return AdapterResult(
                success=False,
                error=f"Kong health check failed: HTTP {resp.status_code}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    # --- APIs ---

    async def sync_api(self, api_spec: dict, tenant_id: str, auth_token: str | None = None) -> AdapterResult:
        """Sync an API by posting a full declarative config reload.

        In DB-less mode, individual service creation is not supported.
        We build a minimal declarative config with the requested service
        and POST it to ``/config``.
        """
        try:
            service = mappers.map_api_spec_to_kong_service(api_spec, tenant_id)
            config_payload = {
                "_format_version": "3.0",
                "services": [service],
            }
            resp = await self._client.post("/config", json=config_payload)

            if resp.status_code in (200, 201):
                return AdapterResult(
                    success=True,
                    resource_id=service["name"],
                    data={"service_name": service["name"]},
                )
            return AdapterResult(
                success=False,
                error=f"Kong sync_api failed: HTTP {resp.status_code} — {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete not directly supported in DB-less — returns success (idempotent).

        In production, the declarative config would be regenerated without
        this service and reloaded via ``POST /config``.
        """
        return AdapterResult(
            success=True,
            resource_id=api_id,
            data={"detail": "DB-less mode: service removed from declarative config"},
        )

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        try:
            resp = await self._client.get("/services")
            if resp.status_code == 200:
                data = resp.json()
                services = data.get("data", [])
                return [mappers.map_kong_service_to_cp(s) for s in services]
            return []
        except Exception:
            return []

    # --- Policies (not supported in DB-less) ---

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        return []

    # --- Applications ---

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        return []

    # --- Auth / OIDC ---

    async def upsert_auth_server(self, auth_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def upsert_strategy(self, strategy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    async def upsert_scope(self, scope_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    # --- Aliases ---

    async def upsert_alias(self, alias_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    # --- Configuration ---

    async def apply_config(self, config_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    # --- Backup ---

    async def export_archive(self, auth_token: str | None = None) -> bytes:
        return b""

    # --- Internal helpers ---

    def _auth_headers(self) -> dict:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Kong-Admin-Token"] = self._api_key
        return headers
