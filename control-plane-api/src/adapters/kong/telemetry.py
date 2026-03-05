"""Kong Gateway telemetry adapter.

Push path (primary): configures the ``http-log`` plugin to POST access
logs to the STOA telemetry ingest endpoint via declarative config reload.

Pull path: Kong DB-less has no native log query API — returns empty.

Metrics: ``GET /status`` returns connection and timer stats.

See CAB-1683 for context.
"""

import logging
from datetime import datetime

import httpx

from ..gateway_adapter_interface import AdapterResult
from ..telemetry_interface import TelemetryAdapterInterface

logger = logging.getLogger(__name__)

_PLUGIN_NAME = "http-log"
_PLUGIN_TAG = "stoa-telemetry"


class KongTelemetryAdapter(TelemetryAdapterInterface):
    """Kong DB-less telemetry — push via http-log plugin, metrics via /status."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._base_url = self._config.get("base_url", "http://localhost:8001")
        auth_config = self._config.get("auth_config", {})
        self._api_key = auth_config.get("api_key", "") if isinstance(auth_config, dict) else ""

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Kong-Admin-Token"] = self._api_key
        return headers

    async def get_access_logs(self, since: datetime, limit: int = 1000) -> list[dict]:
        """Kong DB-less has no log query API — use push path instead."""
        return []

    async def get_metrics_snapshot(self) -> dict:
        """GET /status for connection and timer metrics."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url, headers=self._auth_headers(), timeout=10.0) as client:
                resp = await client.get("/status")
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "connections_active": data.get("server", {}).get("connections_active", 0),
                        "connections_accepted": data.get("server", {}).get("connections_accepted", 0),
                        "total_requests": data.get("server", {}).get("total_requests", 0),
                        "database_reachable": data.get("database", {}).get("reachable", False),
                    }
                return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning("Kong metrics fetch failed: %s", e)
            return {"error": str(e)}

    async def setup_push_subscription(self, webhook_url: str) -> AdapterResult:
        """Configure http-log plugin via declarative config reload.

        Steps:
        1. GET current config (services, plugins, consumers)
        2. Upsert global http-log plugin targeting webhook_url
        3. POST /config to reload
        """
        try:
            async with httpx.AsyncClient(base_url=self._base_url, headers=self._auth_headers(), timeout=30.0) as client:
                # Fetch current plugins
                resp = await client.get("/plugins")
                existing_plugins: list[dict] = []
                if resp.status_code == 200:
                    for p in resp.json().get("data", []):
                        tags = p.get("tags") or []
                        if p.get("name") == _PLUGIN_NAME and _PLUGIN_TAG in tags:
                            continue  # Remove existing stoa telemetry http-log
                        existing_plugins.append(
                            {
                                "name": p.get("name", ""),
                                "config": p.get("config", {}),
                                "tags": tags,
                            }
                        )

                # Fetch current services (needed for full declarative config)
                services_resp = await client.get("/services")
                services = []
                if services_resp.status_code == 200:
                    for svc in services_resp.json().get("data", []):
                        entry = {
                            "name": svc.get("name", ""),
                            "url": f"{svc.get('protocol', 'http')}://{svc.get('host', '')}:{svc.get('port', 80)}{svc.get('path') or ''}",
                        }
                        routes_resp = await client.get(f"/services/{svc['id']}/routes")
                        if routes_resp.status_code == 200:
                            entry["routes"] = [
                                {"name": r.get("name", ""), "paths": r.get("paths", [])}
                                for r in routes_resp.json().get("data", [])
                            ]
                        services.append(entry)

                # Add stoa http-log plugin
                http_log_plugin = {
                    "name": _PLUGIN_NAME,
                    "config": {
                        "http_endpoint": webhook_url,
                        "method": "POST",
                        "content_type": "application/json",
                        "flush_timeout": 2,
                        "retry_count": 3,
                    },
                    "tags": [_PLUGIN_TAG],
                }
                existing_plugins.append(http_log_plugin)

                config_payload = {
                    "_format_version": "3.0",
                    "services": services,
                    "plugins": existing_plugins,
                }

                reload_resp = await client.post("/config", json=config_payload)
                if reload_resp.status_code in (200, 201):
                    return AdapterResult(success=True, data={"webhook_url": webhook_url})
                return AdapterResult(
                    success=False,
                    error=f"Kong config reload failed: HTTP {reload_resp.status_code}",
                )
        except Exception as e:
            logger.warning("Kong push subscription setup failed: %s", e)
            return AdapterResult(success=False, error=str(e))


def normalize_kong_log(entry: dict) -> dict:
    """Normalize a Kong http-log entry to the common telemetry schema."""
    request = entry.get("request", {})
    response = entry.get("response", {})
    latencies = entry.get("latencies", {})
    service = entry.get("service", {})
    return {
        "timestamp": entry.get("started_at", ""),
        "gateway_type": "kong",
        "method": request.get("method", "UNKNOWN"),
        "path": request.get("uri", request.get("url", "")),
        "status": response.get("status", 0),
        "latency_ms": latencies.get("proxy", latencies.get("request", 0)),
        "tenant_id": service.get("name", "platform"),
        "request_id": request.get("headers", {}).get("x-request-id", ""),
    }
