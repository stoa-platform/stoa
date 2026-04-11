"""Gravitee APIM telemetry adapter.

Pull path (primary): queries Gravitee analytics API for request logs.
Push path: Gravitee can be configured with a TCP Reporter but this
requires gravitee.yml changes (not available via Management API).

Metrics: uses the analytics endpoint for request counts and latencies.

See CAB-1683 for context.
"""

import logging
from base64 import b64encode
from datetime import UTC, datetime

import httpx

from ..gateway_adapter_interface import AdapterResult
from ..telemetry_interface import TelemetryAdapterInterface

logger = logging.getLogger(__name__)

_MGMT_V2 = "/management/v2/environments/DEFAULT"


class GraviteeTelemetryAdapter(TelemetryAdapterInterface):
    """Gravitee APIM telemetry — pull via analytics API."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._base_url = self._config.get("base_url", "http://localhost:8083")
        auth_config = self._config.get("auth_config") or {}
        if not isinstance(auth_config, dict) or not auth_config.get("username") or not auth_config.get("password"):
            raise ValueError(
                "GraviteeTelemetryAdapter requires auth_config with 'username' and 'password'. "
                "Credentials must come from Vault, never hardcoded defaults."
            )
        self._username = auth_config["username"]
        self._password = auth_config["password"]

    def _auth_headers(self) -> dict[str, str]:
        creds = b64encode(f"{self._username}:{self._password}".encode()).decode()
        return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

    async def get_access_logs(self, since: datetime, limit: int = 1000) -> list[dict]:
        """Query Gravitee analytics for platform request logs."""
        try:
            since_ms = int(since.timestamp() * 1000)
            now_ms = int(datetime.now(UTC).timestamp() * 1000)
            url = f"{_MGMT_V2}/platform/logs?from={since_ms}&to={now_ms}&size={limit}"

            async with httpx.AsyncClient(base_url=self._base_url, headers=self._auth_headers(), timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    logs = data.get("logs", data.get("data", []))
                    return [_normalize_gravitee_log(entry) for entry in logs]
                logger.warning("Gravitee logs fetch returned HTTP %d", resp.status_code)
                return []
        except Exception as e:
            logger.warning("Gravitee access logs fetch failed: %s", e)
            return []

    async def get_metrics_snapshot(self) -> dict:
        """Query Gravitee platform analytics for request count stats."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url, headers=self._auth_headers(), timeout=10.0) as client:
                url = f"{_MGMT_V2}/platform/analytics?type=count"
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning("Gravitee metrics fetch failed: %s", e)
            return {"error": str(e)}

    async def setup_push_subscription(self, webhook_url: str) -> AdapterResult:
        """Gravitee push requires gravitee.yml TCP Reporter config — not available via API."""
        return AdapterResult(
            success=False,
            error="Gravitee push requires gravitee.yml TCP Reporter configuration (not available via Management API)",
        )


def _normalize_gravitee_log(entry: dict) -> dict:
    """Normalize a Gravitee log entry to the common telemetry schema."""
    timestamp = entry.get("timestamp", entry.get("@timestamp", ""))
    if isinstance(timestamp, int):
        timestamp = datetime.fromtimestamp(timestamp / 1000, tz=UTC).isoformat()
    return {
        "timestamp": timestamp,
        "gateway_type": "gravitee",
        "method": entry.get("method", entry.get("http-method", "UNKNOWN")),
        "path": entry.get("path", entry.get("uri", "")),
        "status": entry.get("status", entry.get("response-status", 0)),
        "latency_ms": entry.get("response-time", entry.get("responseTime", 0)),
        "tenant_id": entry.get("tenant", "platform"),
        "request_id": entry.get("requestId", entry.get("request-id", "")),
    }
