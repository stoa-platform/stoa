"""webMethods API Gateway adapter — implements GatewayAdapterInterface.

Delegates HTTP communication to the existing GatewayAdminService and
translates between the gateway-agnostic adapter contract and the
webMethods-specific REST API at /rest/apigateway/*.
"""

import logging
from typing import Optional

from ..gateway_adapter_interface import GatewayAdapterInterface, AdapterResult
from . import mappers

logger = logging.getLogger(__name__)


class WebMethodsGatewayAdapter(GatewayAdapterInterface):
    """webMethods API Gateway implementation of the Gateway Adapter.

    Wraps the existing GatewayAdminService, adding the adapter contract
    on top. All methods are idempotent where the underlying API allows it.
    """

    def __init__(self):
        # Lazy import to avoid circular dependency during module load
        from ...services.gateway_service import GatewayAdminService
        self._svc = GatewayAdminService()

    # --- Lifecycle ---

    async def health_check(self) -> AdapterResult:
        try:
            result = await self._svc.health_check()
            return AdapterResult(success=True, data=result)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def connect(self) -> None:
        await self._svc.connect()

    async def disconnect(self) -> None:
        await self._svc.disconnect()

    # --- APIs ---

    async def sync_api(
        self, api_spec: dict, tenant_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            result = await self._svc.import_api(
                api_name=api_spec["apiName"],
                api_version=api_spec["apiVersion"],
                openapi_url=api_spec.get("url"),
                openapi_spec=api_spec.get("apiDefinition"),
                api_type=api_spec.get("type", "openapi"),
                auth_token=auth_token,
            )
            api_id = (
                result.get("apiResponse", {}).get("api", {}).get("id", "")
            )
            return AdapterResult(success=True, resource_id=api_id, data=result)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(
        self, api_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            await self._svc.delete_api(api_id, auth_token=auth_token)
            return AdapterResult(success=True, resource_id=api_id)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_apis(self, auth_token: Optional[str] = None) -> list[dict]:
        return await self._svc.list_apis(auth_token=auth_token)

    # --- Policies ---

    async def upsert_policy(
        self, policy_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            payload = mappers.map_policy_to_webmethods(policy_spec)

            # Check if policy exists by name
            existing = await self.list_policies(auth_token=auth_token)
            policy_name = policy_spec.get("name", "")
            existing_policy = next(
                (p for p in existing if p.get("policyName") == policy_name or p.get("name") == policy_name),
                None,
            )

            if existing_policy:
                policy_id = existing_policy.get("id", "")
                result = await self._svc._request(
                    "PUT", f"/policyActions/{policy_id}",
                    auth_token=auth_token,
                    json=payload["policyAction"],
                )
                return AdapterResult(success=True, resource_id=policy_id, data=result)
            else:
                result = await self._svc._request(
                    "POST", "/policyActions",
                    auth_token=auth_token,
                    json=payload["policyAction"],
                )
                policy_id = result.get("policyAction", {}).get("id", "")
                return AdapterResult(success=True, resource_id=policy_id, data=result)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_policy(
        self, policy_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            await self._svc._request(
                "DELETE", f"/policyActions/{policy_id}", auth_token=auth_token
            )
            return AdapterResult(success=True, resource_id=policy_id)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_policies(self, auth_token: Optional[str] = None) -> list[dict]:
        result = await self._svc._request("GET", "/policies", auth_token=auth_token)
        return result.get("policies", [])

    # --- Applications ---

    async def provision_application(
        self, app_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            result = await self._svc.provision_application(
                subscription_id=app_spec["subscription_id"],
                application_name=app_spec["application_name"],
                api_id=app_spec["api_id"],
                tenant_id=app_spec["tenant_id"],
                subscriber_email=app_spec.get("subscriber_email", ""),
                correlation_id=app_spec.get("correlation_id", ""),
                auth_token=auth_token,
            )
            return AdapterResult(
                success=True,
                resource_id=result["app_id"],
                data=result,
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def deprovision_application(
        self, app_id: str, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            await self._svc.deprovision_application(
                app_id=app_id,
                correlation_id="adapter",
                auth_token=auth_token,
            )
            return AdapterResult(success=True, resource_id=app_id)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_applications(self, auth_token: Optional[str] = None) -> list[dict]:
        return await self._svc.list_applications(auth_token=auth_token)

    # --- Auth / OIDC ---

    async def upsert_auth_server(
        self, auth_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            payload = mappers.map_auth_server_to_webmethods(auth_spec)

            # Check if auth server alias exists
            existing = await self._svc.list_aliases(auth_token=auth_token)
            existing_alias = next(
                (a for a in existing if a.get("name") == auth_spec["name"] and a.get("type") == "authServerAlias"),
                None,
            )

            if existing_alias:
                alias_id = existing_alias.get("id", "")
                result = await self._svc._request(
                    "PUT", f"/alias/{alias_id}", auth_token=auth_token, json=payload
                )
                return AdapterResult(success=True, resource_id=alias_id, data=result)
            else:
                result = await self._svc._request(
                    "POST", "/alias", auth_token=auth_token, json=payload
                )
                alias_id = result.get("alias", {}).get("id", "")
                return AdapterResult(success=True, resource_id=alias_id, data=result)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def upsert_strategy(
        self, strategy_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            existing = await self._svc.list_strategies(auth_token=auth_token)
            name = strategy_spec.get("name", "")
            existing_strategy = next(
                (s for s in existing if s.get("name") == name), None
            )

            payload = {
                "name": name,
                "description": strategy_spec.get("description", ""),
                "type": strategy_spec.get("type", "OAUTH2"),
                "authServerAlias": strategy_spec["authServerAlias"],
                "clientId": strategy_spec.get("clientId", ""),
                "audience": strategy_spec.get("audience", ""),
            }

            if existing_strategy:
                strategy_id = existing_strategy.get("id", "")
                result = await self._svc._request(
                    "PUT", f"/strategies/{strategy_id}", auth_token=auth_token, json=payload
                )
                return AdapterResult(success=True, resource_id=strategy_id, data=result)
            else:
                result = await self._svc._request(
                    "POST", "/strategies", auth_token=auth_token, json=payload
                )
                strategy_id = result.get("strategy", {}).get("id", "")
                return AdapterResult(success=True, resource_id=strategy_id, data=result)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def upsert_scope(
        self, scope_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            result = await self._svc.create_scope_mapping(
                scope_name=scope_spec["scopeName"],
                description=scope_spec.get("description", ""),
                audience=scope_spec.get("audience", ""),
                api_ids=scope_spec.get("apiIds", []),
                auth_server_alias=scope_spec.get("authServerAlias", "KeycloakOIDC"),
                keycloak_scope=scope_spec.get("keycloakScope", "openid"),
                auth_token=auth_token,
            )
            return AdapterResult(success=True, data=result)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    # --- Aliases ---

    async def upsert_alias(
        self, alias_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            payload = mappers.map_alias_to_webmethods(alias_spec)

            existing = await self._svc.list_aliases(auth_token=auth_token)
            existing_alias = next(
                (a for a in existing if a.get("name") == alias_spec["name"] and a.get("type") != "authServerAlias"),
                None,
            )

            if existing_alias:
                alias_id = existing_alias.get("id", "")
                result = await self._svc._request(
                    "PUT", f"/alias/{alias_id}", auth_token=auth_token, json=payload
                )
                return AdapterResult(success=True, resource_id=alias_id, data=result)
            else:
                result = await self._svc._request(
                    "POST", "/alias", auth_token=auth_token, json=payload
                )
                alias_id = result.get("alias", {}).get("id", "")
                return AdapterResult(success=True, resource_id=alias_id, data=result)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    # --- Configuration ---

    async def apply_config(
        self, config_spec: dict, auth_token: Optional[str] = None
    ) -> AdapterResult:
        try:
            payloads = mappers.map_config_to_webmethods(config_spec)
            results = {}

            for config_key, payload in payloads.items():
                result = await self._svc._request(
                    "PUT", f"/configurations/{config_key}",
                    auth_token=auth_token, json=payload,
                )
                results[config_key] = result

            return AdapterResult(success=True, data=results)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    # --- Backup ---

    async def export_archive(self, auth_token: Optional[str] = None) -> bytes:
        async with self._svc._get_client(auth_token) as client:
            response = await client.request(
                "GET", "/archive",
                params={"include": "api,application,alias,policy"},
            )
            response.raise_for_status()
            return response.content
