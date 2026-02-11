"""Gravitee APIM adapter — implements GatewayAdapterInterface.

Calls the Gravitee Management API (v2) to manage APIs, check health,
and perform CRUD operations. Authenticated via HTTP Basic (admin/admin
by default, configurable via auth_config).

Ref: https://docs.gravitee.io/apim/3.x/apim_installguide_rest_apis_documentation.html
"""

import logging
from base64 import b64encode

import httpx

from ..gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from . import mappers

logger = logging.getLogger(__name__)

_NOT_SUPPORTED = "Not supported by Gravitee adapter"

# Gravitee Management API v2 base path
_MGMT_V2 = "/management/v2/organizations/DEFAULT/environments/DEFAULT"
_MGMT_V1 = "/management/organizations/DEFAULT/environments/DEFAULT"


class GraviteeGatewayAdapter(GatewayAdapterInterface):
    """Gravitee APIM implementation of the Gateway Adapter.

    Communicates with the Gravitee Management API (default port 8083).
    Uses HTTP Basic authentication.
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)
        self._base_url = (config or {}).get("base_url", "http://localhost:8083")
        auth_config = (config or {}).get("auth_config", {})
        if isinstance(auth_config, dict):
            self._username = auth_config.get("username", "admin")
            self._password = auth_config.get("password", "admin")
        else:
            self._username = "admin"
            self._password = "admin"
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
            resp = await client.get(_MGMT_V1)
            if self._client is None:
                await client.aclose()

            if resp.status_code == 200:
                data = resp.json()
                return AdapterResult(
                    success=True,
                    data={
                        "environment": data.get("name", "DEFAULT"),
                        "organization": data.get("organizationId", "DEFAULT"),
                        "version": "4.x",
                    },
                )
            return AdapterResult(
                success=False,
                error=f"Gravitee health check failed: HTTP {resp.status_code}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    # --- APIs ---

    async def sync_api(self, api_spec: dict, tenant_id: str, auth_token: str | None = None) -> AdapterResult:
        try:
            payload = mappers.map_api_spec_to_gravitee_v4(api_spec, tenant_id)
            resp = await self._client.post(f"{_MGMT_V2}/apis", json=payload)

            if resp.status_code in (200, 201):
                data = resp.json()
                return AdapterResult(
                    success=True,
                    resource_id=data.get("id", ""),
                    data={"name": payload["name"]},
                )
            return AdapterResult(
                success=False,
                error=f"Gravitee sync_api failed: HTTP {resp.status_code} — {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        try:
            resp = await self._client.delete(f"{_MGMT_V2}/apis/{api_id}")
            if resp.status_code in (200, 204):
                return AdapterResult(success=True, resource_id=api_id)
            if resp.status_code == 404:
                return AdapterResult(success=True, resource_id=api_id)
            return AdapterResult(
                success=False,
                error=f"Gravitee delete_api failed: HTTP {resp.status_code}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        try:
            resp = await self._client.get(f"{_MGMT_V2}/apis")
            if resp.status_code == 200:
                data = resp.json()
                apis = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(apis, list):
                    return [mappers.map_gravitee_api_to_cp(a) for a in apis]
            return []
        except Exception:
            return []

    # --- Policies ---

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
        credentials = b64encode(f"{self._username}:{self._password}".encode()).decode()
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }
