"""Apigee X Gateway Adapter.

Implements the 8 core methods of GatewayAdapterInterface for Google Apigee X.
Uses Google Cloud bearer token auth and the Apigee Management API v1.

API base: https://apigee.googleapis.com/v1/organizations/{org}
"""

import logging

import httpx

from ..gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from . import mappers

logger = logging.getLogger(__name__)


class ApigeeGatewayAdapter(GatewayAdapterInterface):
    """Adapter for Apigee X (Google Cloud managed)."""

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config=config)
        cfg = config or {}
        self._org = cfg.get("organization", "")
        base_url = cfg.get("base_url", "https://apigee.googleapis.com")
        self._base_url = f"{base_url}/v1/organizations/{self._org}"
        auth_config = cfg.get("auth_config", {})
        self._bearer_token = auth_config.get("bearer_token", "") if isinstance(auth_config, dict) else ""
        self._client: httpx.AsyncClient | None = None

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    async def connect(self) -> None:
        """Create persistent HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._auth_headers(),
            timeout=30.0,
        )

    async def disconnect(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> AdapterResult:
        """Check Apigee connectivity by listing environments."""
        client = self._client or httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._auth_headers(),
            timeout=10.0,
        )
        try:
            resp = await client.get("/environments")
            if resp.status_code == 200:
                return AdapterResult(success=True, data={"status": "healthy"})
            return AdapterResult(
                success=False,
                error=f"Apigee health check failed: HTTP {resp.status_code}",
            )
        except httpx.HTTPError as e:
            return AdapterResult(success=False, error=f"Connection error: {e}")
        finally:
            if self._client is None:
                await client.aclose()

    async def sync_api(
        self,
        api_spec: dict,
        tenant_id: str,
        auth_token: str | None = None,
    ) -> AdapterResult:
        """Create or update an API proxy in Apigee."""
        if not self._client:
            return AdapterResult(success=False, error="Not connected")

        proxy = mappers.map_api_spec_to_apigee_proxy(api_spec, tenant_id)
        proxy_name = proxy["name"]

        # Check if proxy exists
        check_resp = await self._client.get(f"/apis/{proxy_name}")
        if check_resp.status_code == 200:
            # Update existing: Apigee proxies are versioned, create new revision
            logger.info("API proxy %s exists, creating new revision", proxy_name)
        else:
            # Create new proxy
            logger.info("Creating new API proxy: %s", proxy_name)

        body = {
            "name": proxy_name,
            "displayName": proxy.get("displayName", proxy_name),
            "description": proxy.get("description", ""),
            "labels": proxy.get("labels", {}),
        }

        resp = await self._client.post("/apis", json=body)
        if resp.status_code in (200, 201):
            data = resp.json()
            return AdapterResult(
                success=True,
                resource_id=proxy_name,
                data=data,
            )
        return AdapterResult(
            success=False,
            error=f"Failed to sync API: HTTP {resp.status_code} - {resp.text}",
        )

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API proxy from Apigee."""
        if not self._client:
            return AdapterResult(success=False, error="Not connected")

        resp = await self._client.delete(f"/apis/{api_id}")
        if resp.status_code in (200, 204, 404):
            return AdapterResult(success=True, resource_id=api_id)
        return AdapterResult(
            success=False,
            error=f"Failed to delete API: HTTP {resp.status_code} - {resp.text}",
        )

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        """List all API proxies from Apigee."""
        if not self._client:
            return []

        resp = await self._client.get("/apis")
        if resp.status_code != 200:
            logger.warning("Failed to list APIs: HTTP %d", resp.status_code)
            return []

        data = resp.json()
        proxies = data.get("proxies", [])
        return [mappers.map_apigee_proxy_to_cp(p) for p in proxies]

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Create or update a policy as an Apigee API product."""
        if not self._client:
            return AdapterResult(success=False, error="Not connected")

        tenant_id = policy_spec.get("tenant_id", "default")
        product = mappers.map_policy_to_apigee_product(policy_spec, tenant_id)
        product_name = product["name"]

        # Check if product exists
        check_resp = await self._client.get(f"/apiproducts/{product_name}")
        if check_resp.status_code == 200:
            resp = await self._client.put(f"/apiproducts/{product_name}", json=product)
        else:
            resp = await self._client.post("/apiproducts", json=product)

        if resp.status_code in (200, 201):
            return AdapterResult(
                success=True,
                resource_id=product_name,
                data=resp.json(),
            )
        return AdapterResult(
            success=False,
            error=f"Failed to upsert policy: HTTP {resp.status_code} - {resp.text}",
        )

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API product from Apigee."""
        if not self._client:
            return AdapterResult(success=False, error="Not connected")

        resp = await self._client.delete(f"/apiproducts/{policy_id}")
        if resp.status_code in (200, 204, 404):
            return AdapterResult(success=True, resource_id=policy_id)
        return AdapterResult(
            success=False,
            error=f"Failed to delete policy: HTTP {resp.status_code} - {resp.text}",
        )

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        """List API products from Apigee (policies mapped to products)."""
        if not self._client:
            return []

        resp = await self._client.get("/apiproducts")
        if resp.status_code != 200:
            logger.warning("Failed to list policies: HTTP %d", resp.status_code)
            return []

        data = resp.json()
        products = data.get("apiProduct", [])
        # Filter STOA-managed products
        stoa_products = []
        for p in products:
            attrs = {a["name"]: a["value"] for a in p.get("attributes", [])}
            if attrs.get("stoa-managed") == "true":
                stoa_products.append(mappers.map_apigee_product_to_policy(p))
        return stoa_products

    # --- Not supported by Apigee adapter (stubs) ---

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported — Apigee applications managed via separate workflow."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        """Not supported."""
        return []

    async def upsert_auth_server(self, auth_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")

    async def upsert_strategy(self, strategy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")

    async def upsert_scope(self, scope_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")

    async def upsert_alias(self, alias_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")

    async def apply_config(self, config_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")

    async def export_archive(self, auth_token: str | None = None) -> bytes:
        """Not supported."""
        return b""
