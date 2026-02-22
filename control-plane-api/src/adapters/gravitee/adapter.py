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

    API lifecycle: create → start → deploy. Deletion: stop → delete.
    Policies are managed via Plans with flows.
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
        """Sync an API with full lifecycle: create/update → start → deploy.

        1. Check if API exists by name
        2. Create (POST) or update (PUT)
        3. Start the API (POST /_start)
        4. Deploy the API (POST /_deploy)
        """
        try:
            payload = mappers.map_api_spec_to_gravitee_v4(api_spec, tenant_id)
            api_name = payload["name"]

            # Check if API already exists
            existing_id = await self._find_api_by_name(api_name)

            if existing_id:
                # Update existing API
                resp = await self._client.put(f"{_MGMT_V2}/apis/{existing_id}", json=payload)
                if resp.status_code not in (200, 201):
                    return AdapterResult(
                        success=False,
                        error=f"Gravitee update API failed: HTTP {resp.status_code} — {resp.text}",
                    )
                api_id = existing_id
            else:
                # Create new API
                resp = await self._client.post(f"{_MGMT_V2}/apis", json=payload)
                if resp.status_code not in (200, 201):
                    return AdapterResult(
                        success=False,
                        error=f"Gravitee create API failed: HTTP {resp.status_code} — {resp.text}",
                    )
                data = resp.json()
                api_id = data.get("id", "")

            # Start the API
            start_resp = await self._client.post(f"{_MGMT_V2}/apis/{api_id}/_start")
            if start_resp.status_code not in (200, 204, 409):
                # 409 = already started, which is fine
                logger.warning("Gravitee _start returned %d for %s", start_resp.status_code, api_id)

            # Deploy the API
            deploy_resp = await self._client.post(f"{_MGMT_V2}/apis/{api_id}/deployments")
            if deploy_resp.status_code not in (200, 202, 204):
                logger.warning("Gravitee deploy returned %d for %s", deploy_resp.status_code, api_id)

            return AdapterResult(
                success=True,
                resource_id=api_id,
                data={"name": api_name, "started": True},
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API with lifecycle: stop → close plans → delete."""
        try:
            # Stop the API first
            stop_resp = await self._client.post(f"{_MGMT_V2}/apis/{api_id}/_stop")
            if stop_resp.status_code not in (200, 204, 404, 409):
                logger.warning("Gravitee _stop returned %d for %s", stop_resp.status_code, api_id)

            # Close all plans before deletion
            await self._close_all_plans(api_id)

            # Delete the API
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

    # --- Policies (via Plans) ---

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Upsert a policy by creating/updating a Gravitee Plan on the target API."""
        try:
            api_id = policy_spec.get("api_id", "")
            if not api_id:
                return AdapterResult(success=False, error="api_id required for Gravitee policy")

            api_name = policy_spec.get("api_name", api_id)
            plan_payload = mappers.map_policy_to_gravitee_plan(policy_spec, api_name)
            policy_id = policy_spec.get("id", "")

            # Check if plan already exists with this stoa tag
            existing_plan_id = await self._find_plan_by_stoa_id(api_id, policy_id)

            if existing_plan_id:
                resp = await self._client.put(
                    f"{_MGMT_V2}/apis/{api_id}/plans/{existing_plan_id}",
                    json=plan_payload,
                )
            else:
                resp = await self._client.post(
                    f"{_MGMT_V2}/apis/{api_id}/plans",
                    json=plan_payload,
                )

            if resp.status_code in (200, 201):
                data = resp.json()
                plan_id = data.get("id", existing_plan_id or "")

                # Publish the plan
                pub_resp = await self._client.post(f"{_MGMT_V2}/apis/{api_id}/plans/{plan_id}/_publish")
                if pub_resp.status_code not in (200, 204, 409):
                    logger.warning("Plan publish returned %d", pub_resp.status_code)

                return AdapterResult(
                    success=True,
                    resource_id=policy_id,
                    data={"plan_id": plan_id},
                )
            return AdapterResult(
                success=False,
                error=f"Gravitee upsert_policy failed: HTTP {resp.status_code} — {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete a policy by closing and removing its Gravitee Plan.

        Requires the api_id to be encoded in the policy_id as 'api_id:policy_id',
        or searches all APIs.
        """
        try:
            # policy_id format: "api_id:stoa_policy_id" or just "stoa_policy_id"
            if ":" in policy_id:
                api_id, stoa_id = policy_id.split(":", 1)
            else:
                stoa_id = policy_id
                api_id = ""

            if api_id:
                plan_id = await self._find_plan_by_stoa_id(api_id, stoa_id)
                if plan_id:
                    await self._close_and_delete_plan(api_id, plan_id)
            else:
                # Search all APIs for this policy
                apis = await self.list_apis()
                for api in apis:
                    aid = api.get("id", "")
                    plan_id = await self._find_plan_by_stoa_id(aid, stoa_id)
                    if plan_id:
                        await self._close_and_delete_plan(aid, plan_id)
                        break

            return AdapterResult(success=True, resource_id=policy_id)
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        """List all STOA-managed plans across all APIs."""
        try:
            result: list[dict] = []
            apis = await self.list_apis()
            for api in apis:
                api_id = api.get("id", "")
                if not api_id:
                    continue
                plans = await self._list_api_plans(api_id)
                for plan in plans:
                    name = plan.get("name", "")
                    if name.startswith("stoa-"):
                        result.append(mappers.map_gravitee_plan_to_policy(plan))
            return result
        except Exception:
            return []

    # --- Applications ---

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Provision a consumer application on Gravitee.

        1. Create Application
        2. Ensure a Plan exists on the target API
        3. Subscribe the application to the plan
        """
        try:
            app_payload = mappers.map_app_spec_to_gravitee_app(app_spec)
            api_id = app_spec.get("api_id", "")

            # Create application
            resp = await self._client.post(f"{_MGMT_V1}/applications", json=app_payload)
            if resp.status_code not in (200, 201):
                return AdapterResult(
                    success=False,
                    error=f"Gravitee create app failed: HTTP {resp.status_code} — {resp.text}",
                )
            app_data = resp.json()
            app_id = app_data.get("id", "")

            # Find or create a rate-limit plan on the API
            if api_id:
                plan_id = await self._ensure_rate_limit_plan(api_id, app_spec)
                if plan_id:
                    # Subscribe app to plan
                    sub_resp = await self._client.post(
                        f"{_MGMT_V2}/apis/{api_id}/subscriptions",
                        json={"planId": plan_id, "applicationId": app_id},
                    )
                    if sub_resp.status_code in (200, 201):
                        sub_data = sub_resp.json()
                        return AdapterResult(
                            success=True,
                            resource_id=app_id,
                            data={
                                "application_id": app_id,
                                "subscription_id": sub_data.get("id", ""),
                                "plan_id": plan_id,
                            },
                        )
                    logger.warning(
                        "Gravitee subscription failed: %d — %s",
                        sub_resp.status_code,
                        sub_resp.text,
                    )

            return AdapterResult(
                success=True,
                resource_id=app_id,
                data={"application_id": app_id},
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        """Remove an application: close subscriptions → delete app."""
        try:
            # Close active subscriptions for this app
            subs_resp = await self._client.get(
                f"{_MGMT_V1}/applications/{app_id}/subscriptions",
                params={"status": "ACCEPTED"},
            )
            if subs_resp.status_code == 200:
                subs = subs_resp.json()
                sub_list = subs.get("data", subs) if isinstance(subs, dict) else subs
                if isinstance(sub_list, list):
                    for sub in sub_list:
                        sub_id = sub.get("id", "")
                        if sub_id:
                            await self._client.post(f"{_MGMT_V1}/applications/{app_id}/subscriptions/{sub_id}/_close")

            # Delete the application
            resp = await self._client.delete(f"{_MGMT_V1}/applications/{app_id}")
            if resp.status_code in (200, 204, 404):
                return AdapterResult(success=True, resource_id=app_id)
            return AdapterResult(
                success=False,
                error=f"Gravitee delete app failed: HTTP {resp.status_code}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        """List all applications."""
        try:
            resp = await self._client.get(f"{_MGMT_V1}/applications")
            if resp.status_code == 200:
                data = resp.json()
                apps = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(apps, list):
                    return [mappers.map_gravitee_app_to_cp(a) for a in apps]
            return []
        except Exception:
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

    async def deploy_contract(self, contract_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=False, error=_NOT_SUPPORTED)

    # --- Internal helpers ---

    def _auth_headers(self) -> dict:
        credentials = b64encode(f"{self._username}:{self._password}".encode()).decode()
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    async def _find_api_by_name(self, name: str) -> str | None:
        """Find an API by name, return its ID or None."""
        try:
            resp = await self._client.get(f"{_MGMT_V2}/apis", params={"q": name})
            if resp.status_code == 200:
                data = resp.json()
                apis = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(apis, list):
                    for api in apis:
                        if api.get("name") == name:
                            return api.get("id")
        except Exception as e:
            logger.warning("Failed to search Gravitee APIs: %s", e)
        return None

    async def _list_api_plans(self, api_id: str) -> list[dict]:
        """List all plans for a given API."""
        try:
            resp = await self._client.get(f"{_MGMT_V2}/apis/{api_id}/plans")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", data) if isinstance(data, (dict, list)) else []
        except Exception as e:
            logger.warning("Failed to list plans for %s: %s", api_id, e)
        return []

    async def _find_plan_by_stoa_id(self, api_id: str, stoa_policy_id: str) -> str | None:
        """Find a plan by its STOA name pattern (stoa-*-{policy_id})."""
        plans = await self._list_api_plans(api_id)
        suffix = f"-{stoa_policy_id}"
        if isinstance(plans, list):
            for plan in plans:
                name = plan.get("name", "")
                if name.startswith("stoa-") and name.endswith(suffix):
                    return plan.get("id")
        return None

    async def _close_all_plans(self, api_id: str) -> None:
        """Close all plans for an API (required before deletion)."""
        plans = await self._list_api_plans(api_id)
        if isinstance(plans, list):
            for plan in plans:
                plan_id = plan.get("id", "")
                status = plan.get("status", "")
                if plan_id and status != "CLOSED":
                    await self._client.post(f"{_MGMT_V2}/apis/{api_id}/plans/{plan_id}/_close")

    async def _close_and_delete_plan(self, api_id: str, plan_id: str) -> None:
        """Close and delete a specific plan."""
        await self._client.post(f"{_MGMT_V2}/apis/{api_id}/plans/{plan_id}/_close")
        await self._client.delete(f"{_MGMT_V2}/apis/{api_id}/plans/{plan_id}")

    async def _ensure_rate_limit_plan(self, api_id: str, app_spec: dict) -> str | None:
        """Ensure a rate-limit plan exists on the API, create if needed."""
        subscription_id = app_spec.get("subscription_id", "default")
        rate_per_minute = app_spec.get("rate_limit_per_minute")
        rate_per_second = app_spec.get("rate_limit_per_second")

        if not rate_per_minute and not rate_per_second:
            # Check for existing open plans
            plans = await self._list_api_plans(api_id)
            if isinstance(plans, list):
                for plan in plans:
                    if plan.get("status") in ("PUBLISHED", "STAGING"):
                        return plan.get("id")
            return None

        max_requests = rate_per_minute or (rate_per_second * 60 if rate_per_second else 100)
        policy_spec = {
            "id": f"quota-{subscription_id}",
            "type": "rate_limit",
            "config": {"maxRequests": max_requests, "intervalSeconds": 60},
        }
        result = await self.upsert_policy({**policy_spec, "api_id": api_id})
        if result.success and result.data:
            return result.data.get("plan_id")
        return None
