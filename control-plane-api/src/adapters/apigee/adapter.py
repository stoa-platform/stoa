"""Apigee X Gateway Adapter.

Implements GatewayAdapterInterface for Google Apigee X.
Uses Google Cloud bearer token auth and the Apigee Management API v1.

API base: https://apigee.googleapis.com/v1/organizations/{org}

Concept mapping:
  - STOA API → Apigee API Proxy
  - STOA Policy → Apigee API Product (quota via product-level fields)
  - STOA Application → Apigee Developer App (under a STOA-managed developer)
"""

import logging

import httpx

from ..gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from . import mappers

logger = logging.getLogger(__name__)

# Default developer email used for STOA-managed apps
_STOA_DEVELOPER_EMAIL = "stoa-platform@gostoa.dev"


class ApigeeGatewayAdapter(GatewayAdapterInterface):
    """Adapter for Apigee X (Google Cloud managed).

    Config dict keys:
        - organization: Apigee organization name
        - auth_config.bearer_token: Google Cloud bearer token
        - base_url (optional): override endpoint (default: https://apigee.googleapis.com)
    """

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
        headers: dict[str, str] = {"Content-Type": "application/json"}
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

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        """Return (client, should_close_after). Creates ephemeral client if not connected."""
        if self._client:
            return self._client, False
        return (
            httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._auth_headers(),
                timeout=30.0,
            ),
            True,
        )

    # --- Lifecycle ---

    async def health_check(self) -> AdapterResult:
        """Check Apigee connectivity by listing environments."""
        client, close_after = self._get_client()
        try:
            resp = await client.get("/environments")
            if resp.status_code == 200:
                data = resp.json()
                return AdapterResult(
                    success=True,
                    data={
                        "status": "healthy",
                        "organization": self._org,
                        "environments": data if isinstance(data, list) else [],
                    },
                )
            return AdapterResult(
                success=False,
                error=f"Apigee health check failed: HTTP {resp.status_code}",
            )
        except httpx.HTTPError as e:
            return AdapterResult(success=False, error=f"Connection error: {e}")
        finally:
            if close_after:
                await client.aclose()

    # --- APIs (Proxies) ---

    async def sync_api(
        self,
        api_spec: dict,
        tenant_id: str,
        auth_token: str | None = None,
    ) -> AdapterResult:
        """Create or update an API proxy in Apigee."""
        try:
            client, close_after = self._get_client()
            try:
                proxy = mappers.map_api_spec_to_apigee_proxy(api_spec, tenant_id)
                proxy_name = proxy["name"]

                # Check if proxy exists (Apigee proxies are versioned)
                check_resp = await client.get(f"/apis/{proxy_name}")
                if check_resp.status_code == 200:
                    logger.info("API proxy %s exists, creating new revision", proxy_name)
                else:
                    logger.info("Creating new API proxy: %s", proxy_name)

                body = {
                    "name": proxy_name,
                    "displayName": proxy.get("displayName", proxy_name),
                    "description": proxy.get("description", ""),
                    "labels": proxy.get("labels", {}),
                }

                resp = await client.post("/apis", json=body)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return AdapterResult(success=True, resource_id=proxy_name, data=data)
                return AdapterResult(
                    success=False,
                    error=f"Failed to sync API: HTTP {resp.status_code} - {resp.text}",
                )
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API proxy from Apigee."""
        try:
            client, close_after = self._get_client()
            try:
                resp = await client.delete(f"/apis/{api_id}")
                if resp.status_code in (200, 204, 404):
                    return AdapterResult(success=True, resource_id=api_id)
                return AdapterResult(
                    success=False,
                    error=f"Failed to delete API: HTTP {resp.status_code} - {resp.text}",
                )
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        """List all API proxies from Apigee."""
        try:
            client, close_after = self._get_client()
            try:
                resp = await client.get("/apis")
                if resp.status_code != 200:
                    logger.warning("Failed to list APIs: HTTP %d", resp.status_code)
                    return []

                data = resp.json()
                proxies = data.get("proxies", [])
                return [mappers.map_apigee_proxy_to_cp(p) for p in proxies]
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            logger.warning("Failed to list APIs: %s", e)
            return []

    # --- Policies (API Products) ---

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Create or update a policy as an Apigee API product."""
        try:
            client, close_after = self._get_client()
            try:
                tenant_id = policy_spec.get("tenant_id", "default")
                product = mappers.map_policy_to_apigee_product(policy_spec, tenant_id)
                product_name = product["name"]

                # Check if product exists → PUT (update) or POST (create)
                check_resp = await client.get(f"/apiproducts/{product_name}")
                if check_resp.status_code == 200:
                    resp = await client.put(f"/apiproducts/{product_name}", json=product)
                else:
                    resp = await client.post("/apiproducts", json=product)

                if resp.status_code in (200, 201):
                    return AdapterResult(success=True, resource_id=product_name, data=resp.json())
                return AdapterResult(
                    success=False,
                    error=f"Failed to upsert policy: HTTP {resp.status_code} - {resp.text}",
                )
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API product from Apigee."""
        try:
            client, close_after = self._get_client()
            try:
                resp = await client.delete(f"/apiproducts/{policy_id}")
                if resp.status_code in (200, 204, 404):
                    return AdapterResult(success=True, resource_id=policy_id)
                return AdapterResult(
                    success=False,
                    error=f"Failed to delete policy: HTTP {resp.status_code} - {resp.text}",
                )
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        """List API products from Apigee (STOA-managed only)."""
        try:
            client, close_after = self._get_client()
            try:
                resp = await client.get("/apiproducts")
                if resp.status_code != 200:
                    logger.warning("Failed to list policies: HTTP %d", resp.status_code)
                    return []

                data = resp.json()
                products = data.get("apiProduct", [])
                stoa_products = []
                for p in products:
                    attrs = {a["name"]: a["value"] for a in p.get("attributes", [])}
                    if attrs.get("stoa-managed") == "true":
                        stoa_products.append(mappers.map_apigee_product_to_policy(p))
                return stoa_products
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            logger.warning("Failed to list policies: %s", e)
            return []

    # --- Applications (Developer Apps) ---

    async def _ensure_developer(self, client: httpx.AsyncClient) -> bool:
        """Ensure the STOA-managed developer exists. Returns True if OK."""
        check = await client.get(f"/developers/{_STOA_DEVELOPER_EMAIL}")
        if check.status_code == 200:
            return True
        # Create the developer
        resp = await client.post(
            "/developers",
            json={
                "email": _STOA_DEVELOPER_EMAIL,
                "firstName": "STOA",
                "lastName": "Platform",
                "userName": "stoa-platform",
                "attributes": [{"name": "stoa-managed", "value": "true"}],
            },
        )
        return resp.status_code in (200, 201, 409)  # 409 = already exists (race)

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Create a Developer App in Apigee."""
        try:
            client, close_after = self._get_client()
            try:
                tenant_id = app_spec.get("tenant_id", "default")
                app = mappers.map_app_spec_to_apigee_developer_app(app_spec, tenant_id)
                app_name = app["name"]

                # Ensure developer exists
                if not await self._ensure_developer(client):
                    return AdapterResult(success=False, error="Failed to ensure STOA developer in Apigee")

                logger.info("Creating developer app %s in Apigee", app_name)
                resp = await client.post(
                    f"/developers/{_STOA_DEVELOPER_EMAIL}/apps",
                    json=app,
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    return AdapterResult(
                        success=True,
                        resource_id=data.get("name", app_name),
                        data=data,
                    )
                return AdapterResult(
                    success=False,
                    error=f"Failed to create app: HTTP {resp.status_code} - {resp.text}",
                )
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete a Developer App from Apigee."""
        try:
            client, close_after = self._get_client()
            try:
                resp = await client.delete(f"/developers/{_STOA_DEVELOPER_EMAIL}/apps/{app_id}")
                if resp.status_code in (200, 204, 404):
                    return AdapterResult(success=True, resource_id=app_id)
                return AdapterResult(
                    success=False,
                    error=f"Failed to delete app: HTTP {resp.status_code} - {resp.text}",
                )
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        """List Developer Apps from Apigee (STOA-managed only)."""
        try:
            client, close_after = self._get_client()
            try:
                resp = await client.get(f"/developers/{_STOA_DEVELOPER_EMAIL}/apps?expand=true")
                if resp.status_code != 200:
                    logger.warning("Failed to list apps: HTTP %d", resp.status_code)
                    return []

                data = resp.json()
                apps = data.get("app", [])
                return [mappers.map_apigee_developer_app_to_cp(a) for a in apps]
            finally:
                if close_after:
                    await client.aclose()
        except Exception as e:
            logger.warning("Failed to list apps: %s", e)
            return []

    # --- Not supported ---

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

    async def deploy_contract(self, contract_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Apigee adapter")
