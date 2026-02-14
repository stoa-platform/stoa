"""Control Plane API client for the operator."""

import logging
import time
from typing import Any

import httpx

from src.config import settings
from src.metrics import record_cp_api_call

logger = logging.getLogger(__name__)


class ControlPlaneClient:
    """Async HTTP client for the STOA Control Plane API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-Operator-Key"] = self._api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=30.0,
        )
        logger.info("CP API client connected to %s", self._base_url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("CP API client closed")

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            msg = "Client not connected — call connect() first"
            raise RuntimeError(msg)
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an HTTP request and record metrics."""
        start = time.monotonic()
        resp = await self.client.request(method, path, **kwargs)
        record_cp_api_call(method, path, str(resp.status_code), time.monotonic() - start)
        return resp

    # --- Gateway Instance methods ---

    async def register_gateway(self, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("POST", "/v1/admin/gateways", json=data)
        resp.raise_for_status()
        return resp.json()

    async def get_gateway(self, gateway_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/v1/admin/gateways/{gateway_id}")
        resp.raise_for_status()
        return resp.json()

    async def update_gateway(self, gateway_id: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("PUT", f"/v1/admin/gateways/{gateway_id}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def delete_gateway(self, gateway_id: str) -> None:
        resp = await self._request("DELETE", f"/v1/admin/gateways/{gateway_id}")
        if resp.status_code == 404:
            logger.info("Gateway %s already deleted (404), treating as success", gateway_id)
            return
        resp.raise_for_status()

    async def list_gateways(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/v1/admin/gateways")
        resp.raise_for_status()
        return resp.json().get("items", [])

    async def health_check_gateway(self, gateway_id: str) -> dict[str, Any]:
        resp = await self._request("POST", f"/v1/admin/gateways/{gateway_id}/health")
        resp.raise_for_status()
        return resp.json()

    async def get_gateway_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a gateway by name (client-side filter)."""
        gateways = await self.list_gateways()
        for gw in gateways:
            if gw.get("name") == name:
                return gw
        return None

    # --- Deployment methods ---

    async def create_deployment(
        self, api_catalog_id: str, gateway_instance_ids: list[str]
    ) -> list[dict[str, Any]]:
        resp = await self._request(
            "POST",
            "/v1/admin/deployments",
            json={"api_catalog_id": api_catalog_id, "gateway_instance_ids": gateway_instance_ids},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_deployment(self, deployment_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/v1/admin/deployments/{deployment_id}")
        resp.raise_for_status()
        return resp.json()

    async def delete_deployment(self, deployment_id: str) -> None:
        resp = await self._request("DELETE", f"/v1/admin/deployments/{deployment_id}")
        if resp.status_code == 404:
            logger.info("Deployment %s already deleted (404), treating as success", deployment_id)
            return
        resp.raise_for_status()

    async def force_sync_deployment(self, deployment_id: str) -> dict[str, Any]:
        resp = await self._request("POST", f"/v1/admin/deployments/{deployment_id}/sync")
        resp.raise_for_status()
        return resp.json()

    async def get_catalog_entries(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/v1/admin/deployments/catalog-entries")
        resp.raise_for_status()
        return resp.json()


cp_client = ControlPlaneClient(
    base_url=settings.CP_API_URL,
    api_key=settings.CP_API_KEY,
)
