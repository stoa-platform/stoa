"""Control Plane API client for the operator."""

import logging
from typing import Any

import httpx

from src.config import settings

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
            headers["X-Gateway-Key"] = self._api_key
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

    async def register_gateway(self, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self.client.post("/v1/admin/gateways", json=data)
        resp.raise_for_status()
        return resp.json()

    async def get_gateway(self, gateway_id: str) -> dict[str, Any]:
        resp = await self.client.get(f"/v1/admin/gateways/{gateway_id}")
        resp.raise_for_status()
        return resp.json()

    async def update_gateway(self, gateway_id: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self.client.put(f"/v1/admin/gateways/{gateway_id}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def delete_gateway(self, gateway_id: str) -> None:
        resp = await self.client.delete(f"/v1/admin/gateways/{gateway_id}")
        resp.raise_for_status()

    async def list_gateways(self) -> list[dict[str, Any]]:
        resp = await self.client.get("/v1/admin/gateways")
        resp.raise_for_status()
        return resp.json().get("items", [])


cp_client = ControlPlaneClient(
    base_url=settings.CP_API_URL,
    api_key=settings.CP_API_KEY,
)
