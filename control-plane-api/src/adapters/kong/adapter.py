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

    State management: all mutations follow the pattern:
    1. Fetch current entities via GET
    2. Merge desired change
    3. POST full declarative config to /config (atomic reload)
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
        """Sync an API using state management: fetch → merge → reload.

        1. GET /services to read current services
        2. Upsert our service by name (replace if exists, add if new)
        3. Collect existing plugins
        4. POST /config with the full merged config
        """
        try:
            service = mappers.map_api_spec_to_kong_service(api_spec, tenant_id)
            current_config = await self._fetch_current_config()
            services = current_config.get("services", [])

            # Upsert: replace existing service by name, or append
            services = [s for s in services if s.get("name") != service["name"]]
            services.append(service)

            config_payload = self._build_config(
                services=services,
                plugins=current_config.get("plugins", []),
                consumers=current_config.get("consumers", []),
            )
            result = await self._reload_config(config_payload)
            if result.success:
                return AdapterResult(
                    success=True,
                    resource_id=service["name"],
                    data={"service_name": service["name"]},
                )
            return result
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete an API: fetch state → remove service → reload config."""
        try:
            current_config = await self._fetch_current_config()
            services = current_config.get("services", [])
            plugins = current_config.get("plugins", [])

            # Remove service and its associated plugins
            services = [s for s in services if s.get("name") != api_id]
            plugins = [p for p in plugins if p.get("service") != api_id]

            config_payload = self._build_config(
                services=services,
                plugins=plugins,
                consumers=current_config.get("consumers", []),
            )
            result = await self._reload_config(config_payload)
            if result.success:
                return AdapterResult(success=True, resource_id=api_id)
            return result
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

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

    # --- Policies ---

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Upsert a policy via declarative config: fetch → merge plugin → reload."""
        try:
            service_name = policy_spec.get("api_id", "")
            plugin = mappers.map_policy_to_kong_plugin(policy_spec, service_name)
            policy_id = policy_spec.get("id", "")

            current_config = await self._fetch_current_config()
            plugins = current_config.get("plugins", [])

            # Remove existing plugin with same stoa-policy tag
            tag = f"stoa-policy-{policy_id}"
            plugins = [p for p in plugins if tag not in p.get("tags", [])]
            plugins.append(plugin)

            config_payload = self._build_config(
                services=current_config.get("services", []),
                plugins=plugins,
                consumers=current_config.get("consumers", []),
            )
            result = await self._reload_config(config_payload)
            if result.success:
                return AdapterResult(
                    success=True,
                    resource_id=policy_id,
                    data={"plugin_name": plugin["name"], "service": service_name},
                )
            return result
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        """Delete a policy: fetch → remove plugin by stoa tag → reload."""
        try:
            current_config = await self._fetch_current_config()
            plugins = current_config.get("plugins", [])

            tag = f"stoa-policy-{policy_id}"
            plugins = [p for p in plugins if tag not in p.get("tags", [])]

            config_payload = self._build_config(
                services=current_config.get("services", []),
                plugins=plugins,
                consumers=current_config.get("consumers", []),
            )
            result = await self._reload_config(config_payload)
            if result.success:
                return AdapterResult(success=True, resource_id=policy_id)
            return result
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        """List all plugins managed by STOA (identified by stoa-policy-* tags)."""
        try:
            resp = await self._client.get("/plugins")
            if resp.status_code == 200:
                data = resp.json()
                plugins = data.get("data", [])
                result = []
                for p in plugins:
                    tags = p.get("tags") or []
                    if any(t.startswith("stoa-policy-") for t in tags):
                        result.append(mappers.map_kong_plugin_to_policy(p))
                return result
            return []
        except Exception:
            return []

    # --- Applications ---

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        """Provision a consumer in Kong declarative config.

        Adds a consumer with key-auth credentials and optional rate-limiting.
        """
        try:
            consumer = mappers.map_app_spec_to_kong_consumer(app_spec)
            current_config = await self._fetch_current_config()
            consumers = current_config.get("consumers", [])

            # Upsert: replace existing consumer by username
            consumers = [c for c in consumers if c.get("username") != consumer["username"]]
            consumers.append(consumer)

            config_payload = self._build_config(
                services=current_config.get("services", []),
                plugins=current_config.get("plugins", []),
                consumers=consumers,
            )
            result = await self._reload_config(config_payload)
            if result.success:
                return AdapterResult(
                    success=True,
                    resource_id=consumer["username"],
                    data={"consumer": consumer["username"]},
                )
            return result
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        """Remove a consumer from Kong declarative config."""
        try:
            current_config = await self._fetch_current_config()
            consumers = current_config.get("consumers", [])

            consumers = [c for c in consumers if c.get("username") != app_id]

            config_payload = self._build_config(
                services=current_config.get("services", []),
                plugins=current_config.get("plugins", []),
                consumers=consumers,
            )
            result = await self._reload_config(config_payload)
            if result.success:
                return AdapterResult(success=True, resource_id=app_id)
            return result
        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        """List consumers managed by STOA (identified by stoa-consumer-* tags)."""
        try:
            resp = await self._client.get("/consumers")
            if resp.status_code == 200:
                data = resp.json()
                consumers = data.get("data", [])
                result = []
                for c in consumers:
                    tags = c.get("tags") or []
                    if any(t.startswith("stoa-consumer-") for t in tags):
                        result.append(mappers.map_kong_consumer_to_cp(c))
                return result
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
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Kong-Admin-Token"] = self._api_key
        return headers

    async def _fetch_current_config(self) -> dict:
        """Fetch current Kong state via GET endpoints.

        Returns a dict with services, plugins, and consumers arrays.
        Services include an internal ``_id`` field (Kong UUID) used to
        resolve plugin service references; stripped by ``_build_config``.
        """
        services: list[dict] = []
        plugins: list[dict] = []
        consumers: list[dict] = []

        try:
            resp = await self._client.get("/services")
            if resp.status_code == 200:
                data = resp.json()
                for svc in data.get("data", []):
                    service_entry: dict = {
                        "name": svc.get("name", ""),
                        "_id": svc.get("id", ""),
                        "url": f"{svc.get('protocol', 'http')}://{svc.get('host', '')}:{svc.get('port', 80)}{svc.get('path') or ''}",
                    }
                    # Fetch routes for this service
                    routes_resp = await self._client.get(f"/services/{svc['id']}/routes")
                    if routes_resp.status_code == 200:
                        routes_data = routes_resp.json()
                        service_entry["routes"] = [
                            {
                                "name": r.get("name", ""),
                                "paths": r.get("paths", []),
                                "methods": r.get("methods"),
                                "strip_path": r.get("strip_path", True),
                            }
                            for r in routes_data.get("data", [])
                        ]
                    services.append(service_entry)
        except Exception as e:
            logger.warning("Failed to fetch Kong services: %s", e)

        # Build consumer ID→name map (needed to skip consumer-scoped plugins)
        consumer_ids: set[str] = set()
        try:
            resp = await self._client.get("/consumers")
            if resp.status_code == 200:
                data = resp.json()
                for c in data.get("data", []):
                    cid = c.get("id", "")
                    if cid:
                        consumer_ids.add(cid)
                    consumer_entry: dict = {
                        "username": c.get("username", ""),
                        "tags": c.get("tags") or [],
                    }
                    # Fetch credentials for this consumer
                    creds_resp = await self._client.get(f"/consumers/{cid}/key-auth")
                    if creds_resp.status_code == 200:
                        creds_data = creds_resp.json()
                        keys = [{"key": k.get("key", "")} for k in creds_data.get("data", []) if k.get("key")]
                        if keys:
                            consumer_entry["keyauth_credentials"] = keys
                    # Fetch consumer-scoped plugins (inline in declarative config)
                    cplugins_resp = await self._client.get(f"/consumers/{cid}/plugins")
                    if cplugins_resp.status_code == 200:
                        cplugins_data = cplugins_resp.json()
                        inline_plugins = [
                            {"name": cp.get("name", ""), "config": cp.get("config", {})}
                            for cp in cplugins_data.get("data", [])
                        ]
                        if inline_plugins:
                            consumer_entry["plugins"] = inline_plugins
                    consumers.append(consumer_entry)
        except Exception as e:
            logger.warning("Failed to fetch Kong consumers: %s", e)

        try:
            resp = await self._client.get("/plugins")
            if resp.status_code == 200:
                data = resp.json()
                for p in data.get("data", []):
                    # Skip consumer-scoped plugins (handled inline in consumers)
                    consumer_ref = p.get("consumer")
                    if consumer_ref:
                        consumer_id = consumer_ref.get("id", "") if isinstance(consumer_ref, dict) else str(consumer_ref)
                        if consumer_id in consumer_ids:
                            continue

                    # Resolve service name from service.id
                    service_id = ""
                    svc_ref = p.get("service")
                    if isinstance(svc_ref, dict):
                        service_id = svc_ref.get("id", "")
                    elif isinstance(svc_ref, str):
                        service_id = svc_ref

                    plugin_entry: dict = {
                        "name": p.get("name", ""),
                        "config": p.get("config", {}),
                        "tags": p.get("tags") or [],
                    }
                    # Only set service if plugin is service-scoped (not global)
                    if service_id:
                        service_name = self._resolve_service_name(services, service_id)
                        if service_name:
                            plugin_entry["service"] = service_name
                    plugins.append(plugin_entry)
        except Exception as e:
            logger.warning("Failed to fetch Kong plugins: %s", e)

        return {"services": services, "plugins": plugins, "consumers": consumers}

    @staticmethod
    def _resolve_service_name(services: list[dict], service_id: str) -> str:
        """Resolve a service ID (UUID) to its name for declarative config.

        The ``_id`` field is the Kong UUID from GET /services, used to match
        plugin service references back to service names.
        """
        for svc in services:
            if svc.get("_id") == service_id or svc.get("name") == service_id:
                return svc.get("name", "")
        return ""

    @staticmethod
    def _build_config(
        services: list[dict],
        plugins: list[dict],
        consumers: list[dict],
    ) -> dict:
        """Build a full Kong declarative config payload.

        Strips internal ``_id`` fields from services (used only for
        resolving plugin service references during fetch).
        """
        clean_services = [{k: v for k, v in s.items() if k != "_id"} for s in services]
        config: dict = {"_format_version": "3.0", "services": clean_services}
        if plugins:
            config["plugins"] = plugins
        if consumers:
            config["consumers"] = consumers
        return config

    async def _reload_config(self, config_payload: dict) -> AdapterResult:
        """POST /config to atomically reload the full Kong declarative config."""
        try:
            resp = await self._client.post("/config", json=config_payload)
            if resp.status_code in (200, 201):
                return AdapterResult(success=True)
            return AdapterResult(
                success=False,
                error=f"Kong config reload failed: HTTP {resp.status_code} — {resp.text}",
            )
        except Exception as e:
            return AdapterResult(success=False, error=str(e))
