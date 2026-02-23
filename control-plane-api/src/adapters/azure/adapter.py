"""Azure API Management Adapter.

Implements GatewayAdapterInterface for Azure API Management (APIM).
Uses the Azure APIM REST API via httpx (consistent with other STOA adapters).

Auth: Bearer token (Azure AD / Entra ID OAuth2 client credentials flow).

API reference:
  https://learn.microsoft.com/en-us/rest/api/apimanagement/
"""

import logging

import httpx

from ..gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from . import mappers

logger = logging.getLogger(__name__)

# Azure APIM REST API version
_API_VERSION = "2023-09-01-preview"


class AzureApimAdapter(GatewayAdapterInterface):
    """Adapter for Azure API Management.

    Config dict keys:
        - subscription_id: Azure subscription ID
        - resource_group: Azure resource group name
        - service_name: APIM service instance name
        - auth_config.bearer_token: Azure AD bearer token (or managed identity)
        - base_url (optional): override endpoint (for testing, sovereign clouds)
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config=config)
        cfg = config or {}
        self._subscription_id = cfg.get("subscription_id", "")
        self._resource_group = cfg.get("resource_group", "")
        self._service_name = cfg.get("service_name", "")
        auth_config = cfg.get("auth_config", {})
        self._bearer_token = auth_config.get("bearer_token", "") if isinstance(auth_config, dict) else ""

        default_base = "https://management.azure.com"
        self._base_url = cfg.get("base_url", default_base)
        self._client: httpx.AsyncClient | None = None

    @property
    def _service_path(self) -> str:
        """ARM resource path prefix for the APIM instance."""
        return (
            f"/subscriptions/{self._subscription_id}"
            f"/resourceGroups/{self._resource_group}"
            f"/providers/Microsoft.ApiManagement"
            f"/service/{self._service_name}"
        )

    async def connect(self) -> None:
        """Create persistent HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
        )

    async def disconnect(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an authenticated request to the Azure APIM Management API."""
        client = self._client or httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        close_after = self._client is None

        # Append api-version query parameter
        separator = "&" if "?" in path else "?"
        full_path = f"{path}{separator}api-version={_API_VERSION}"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        if extra_headers:
            headers.update(extra_headers)

        try:
            return await client.request(
                method,
                full_path,
                json=json_body,
                headers=headers,
            )
        finally:
            if close_after:
                await client.aclose()

    # --- Lifecycle ---

    async def health_check(self) -> AdapterResult:
        """Check Azure APIM connectivity by getting the service instance."""
        try:
            resp = await self._request("GET", self._service_path)
            if resp.status_code == 200:
                data = resp.json()
                return AdapterResult(
                    success=True,
                    data={
                        "status": "healthy",
                        "service_name": self._service_name,
                        "location": data.get("location", ""),
                        "sku": data.get("sku", {}).get("name", ""),
                    },
                )
            return AdapterResult(
                success=False,
                error=f"Azure APIM health check failed: HTTP {resp.status_code}",
            )
        except httpx.HTTPError as e:
            return AdapterResult(success=False, error=f"Connection error: {e}")

    # --- APIs ---

    async def sync_api(
        self,
        api_spec: dict,
        tenant_id: str,
        auth_token: str | None = None,
    ) -> AdapterResult:
        """Create or update an API in Azure APIM."""
        try:
            azure_api = mappers.map_api_spec_to_azure(api_spec, tenant_id)
            api_id = azure_api["_stoa_api_id"]
            path = f"{self._service_path}/apis/{api_id}"

            # PUT is idempotent (create-or-update)
            logger.info("Syncing API %s to Azure APIM", api_id)
            resp = await self._request("PUT", path, json_body={"properties": azure_api["properties"]})

            if resp.status_code in (200, 201):
                data = resp.json()
                return AdapterResult(
                    success=True,
                    resource_id=data.get("name", api_id),
                    data=data,
                )
            return AdapterResult(
                success=False,
                error=f"Failed to sync API: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API from Azure APIM."""
        try:
            path = f"{self._service_path}/apis/{api_id}"
            resp = await self._request("DELETE", path, extra_headers={"If-Match": "*"})
            if resp.status_code in (200, 204, 404):
                return AdapterResult(success=True, resource_id=api_id)
            return AdapterResult(
                success=False,
                error=f"Failed to delete API: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        """List APIs from Azure APIM (STOA-managed only)."""
        try:
            path = f"{self._service_path}/apis"
            resp = await self._request("GET", path)
            if resp.status_code != 200:
                logger.warning("Failed to list APIs: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            items = data.get("value", [])
            stoa_apis = []
            for item in items:
                # Filter: STOA-managed APIs follow naming convention stoa-{tenant}-*
                name = item.get("name", "")
                if name.startswith("stoa-"):
                    stoa_apis.append(mappers.map_azure_api_to_cp(item))
            return stoa_apis
        except Exception as e:
            logger.warning("Failed to list APIs: %s", e)
            return []

    # --- Policies (Products) ---

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Create or update a Product in Azure APIM (rate-limit via product policy)."""
        try:
            tenant_id = policy_spec.get("tenant_id", "default")
            product = mappers.map_policy_to_azure_product(policy_spec, tenant_id)
            product_id = product["_stoa_product_id"]
            path = f"{self._service_path}/products/{product_id}"

            # PUT is idempotent (create-or-update)
            logger.info("Syncing product %s to Azure APIM", product_id)
            resp = await self._request("PUT", path, json_body={"properties": product["properties"]})

            if resp.status_code not in (200, 201):
                return AdapterResult(
                    success=False,
                    error=f"Failed to upsert product: HTTP {resp.status_code} - {resp.text}",
                )

            product_data = resp.json()
            resource_id = product_data.get("name", product_id)

            # Apply rate-limit policy XML on the product scope
            rate_limit = product.get("_stoa_rate_limit", {})
            if rate_limit:
                policy_xml = mappers.build_rate_limit_policy_xml(
                    calls=rate_limit.get("calls", 100),
                    renewal_period=rate_limit.get("renewal_period", 60),
                )
                policy_path = f"{path}/policies/policy"
                policy_resp = await self._request(
                    "PUT",
                    policy_path,
                    json_body={"properties": {"format": "xml", "value": policy_xml}},
                )
                if policy_resp.status_code not in (200, 201):
                    logger.warning(
                        "Product %s created but policy application failed: HTTP %d",
                        product_id,
                        policy_resp.status_code,
                    )

            return AdapterResult(
                success=True,
                resource_id=resource_id,
                data=product_data,
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete a Product from Azure APIM."""
        try:
            path = f"{self._service_path}/products/{policy_id}"
            resp = await self._request("DELETE", path, extra_headers={"If-Match": "*"})
            if resp.status_code in (200, 204, 404):
                return AdapterResult(success=True, resource_id=policy_id)
            return AdapterResult(
                success=False,
                error=f"Failed to delete product: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        """List Products from Azure APIM (STOA-managed only)."""
        try:
            path = f"{self._service_path}/products"
            resp = await self._request("GET", path)
            if resp.status_code != 200:
                logger.warning("Failed to list products: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            items = data.get("value", [])
            stoa_products = []
            for item in items:
                name = item.get("name", "")
                if name.startswith("stoa-"):
                    stoa_products.append(mappers.map_azure_product_to_policy(item))
            return stoa_products
        except Exception as e:
            logger.warning("Failed to list products: %s", e)
            return []

    # --- Applications (Subscriptions) ---

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Create a Subscription in Azure APIM."""
        try:
            tenant_id = app_spec.get("tenant_id", "default")
            sub = mappers.map_app_spec_to_azure_subscription(app_spec, tenant_id)
            sub_name = sub["_stoa_subscription_name"]
            path = f"{self._service_path}/subscriptions/{sub_name}"

            # Resolve product scope if provided
            product_id = app_spec.get("product_id")
            properties = dict(sub["properties"])
            if product_id:
                properties["scope"] = f"{self._service_path}/products/{product_id}"

            logger.info("Creating subscription %s in Azure APIM", sub_name)
            resp = await self._request("PUT", path, json_body={"properties": properties})

            if resp.status_code in (200, 201):
                data = resp.json()
                return AdapterResult(
                    success=True,
                    resource_id=data.get("name", sub_name),
                    data=data,
                )
            return AdapterResult(
                success=False,
                error=f"Failed to create subscription: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete a Subscription from Azure APIM."""
        try:
            path = f"{self._service_path}/subscriptions/{app_id}"
            resp = await self._request("DELETE", path, extra_headers={"If-Match": "*"})
            if resp.status_code in (200, 204, 404):
                return AdapterResult(success=True, resource_id=app_id)
            return AdapterResult(
                success=False,
                error=f"Failed to delete subscription: HTTP {resp.status_code} - {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        """List Subscriptions from Azure APIM (STOA-managed only)."""
        try:
            path = f"{self._service_path}/subscriptions"
            resp = await self._request("GET", path)
            if resp.status_code != 200:
                logger.warning("Failed to list subscriptions: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            items = data.get("value", [])
            stoa_subs = []
            for item in items:
                name = item.get("name", "")
                if name.startswith("stoa-"):
                    stoa_subs.append(mappers.map_azure_subscription_to_cp(item))
            return stoa_subs
        except Exception as e:
            logger.warning("Failed to list subscriptions: %s", e)
            return []

    # --- Not supported by Azure APIM adapter ---

    async def upsert_auth_server(self, auth_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Azure APIM")

    async def upsert_strategy(self, strategy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Azure APIM")

    async def upsert_scope(self, scope_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Azure APIM")

    async def upsert_alias(self, alias_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Azure APIM")

    async def apply_config(self, config_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Azure APIM")

    async def export_archive(self, auth_token: str | None = None) -> bytes:
        """Not supported."""
        return b""

    async def deploy_contract(self, contract_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Not supported."""
        return AdapterResult(success=False, error="Not supported by Azure APIM")
