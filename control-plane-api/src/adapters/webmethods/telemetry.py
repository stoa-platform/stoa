"""webMethods API Gateway telemetry adapter.

Push path (primary): creates a webhook subscription for transactionalEvents
via ``POST /rest/apigateway/subscriptions``. Auto-recreates on connect()
since trial license resets lose subscriptions.

Pull path (fallback): ``GET /rest/apigateway/transactionalEvents`` with
date range filtering.

Metrics: ``GET /rest/apigateway/is/health`` plus transaction counts.

See CAB-1683 for context.
"""

import logging
from datetime import UTC, datetime

import httpx

from ..gateway_adapter_interface import AdapterResult
from ..telemetry_interface import TelemetryAdapterInterface

logger = logging.getLogger(__name__)

_API_PREFIX = "/rest/apigateway"


class WebMethodsTelemetryAdapter(TelemetryAdapterInterface):
    """webMethods telemetry — push via subscriptions, pull via transactionalEvents."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._base_url = self._config.get("base_url", "http://localhost:5555")
        auth_config = self._config.get("auth_config", {})
        if isinstance(auth_config, dict):
            self._username = auth_config.get("username", "Administrator")
            self._password = auth_config.get("password", "manage")
        else:
            self._username = "Administrator"
            self._password = "manage"

    async def get_access_logs(self, since: datetime, limit: int = 1000) -> list[dict]:
        """Pull transactionalEvents from webMethods."""
        try:
            from_date = since.strftime("%Y-%m-%dT%H:%M:%S")
            to_date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
            url = f"{_API_PREFIX}/transactionalEvents?fromDate={from_date}&toDate={to_date}&size={limit}"

            async with httpx.AsyncClient(
                base_url=self._base_url, auth=(self._username, self._password), timeout=30.0
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("transactionalEvents", data.get("events", []))
                    return [_normalize_wm_event(e) for e in events[:limit]]
                logger.warning("webMethods events fetch returned HTTP %d", resp.status_code)
                return []
        except Exception as e:
            logger.warning("webMethods access logs fetch failed: %s", e)
            return []

    async def get_metrics_snapshot(self) -> dict:
        """GET /rest/apigateway/is/health for gateway health + basic stats."""
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, auth=(self._username, self._password), timeout=10.0
            ) as client:
                resp = await client.get(f"{_API_PREFIX}/is/health")
                if resp.status_code == 200:
                    return dict(resp.json())
                return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning("webMethods health fetch failed: %s", e)
            return {"error": str(e)}

    async def setup_push_subscription(self, webhook_url: str) -> AdapterResult:
        """Create a webhook subscription for transactionalEvents.

        webMethods subscriptions push events to a configured URL.
        Trial license resets lose subscriptions — caller should re-invoke
        after connect() to restore.
        """
        try:
            payload = {
                "eventType": "transactionalEvents",
                "callback": {
                    "endpoint": webhook_url,
                    "method": "POST",
                    "auth": {"type": "none"},
                },
                "active": True,
            }
            async with httpx.AsyncClient(
                base_url=self._base_url, auth=(self._username, self._password), timeout=30.0
            ) as client:
                resp = await client.post(f"{_API_PREFIX}/subscriptions", json=payload)
                if resp.status_code in (200, 201):
                    sub_id = resp.json().get("id", "")
                    return AdapterResult(
                        success=True,
                        data={"subscription_id": sub_id, "webhook_url": webhook_url},
                    )
                return AdapterResult(
                    success=False,
                    error=f"webMethods subscription creation failed: HTTP {resp.status_code} — {resp.text}",
                )
        except Exception as e:
            logger.warning("webMethods push subscription setup failed: %s", e)
            return AdapterResult(success=False, error=str(e))


def _normalize_wm_event(event: dict) -> dict:
    """Normalize a webMethods transactionalEvent to the common telemetry schema."""
    return {
        "timestamp": event.get("creationDate", event.get("eventTimestamp", "")),
        "gateway_type": "webmethods",
        "method": event.get("httpMethod", event.get("operationName", "UNKNOWN")),
        "path": event.get("apiName", event.get("nativeEndpoint", "")),
        "status": event.get("responseCode", event.get("statusCode", 0)),
        "latency_ms": event.get("totalTime", event.get("providerTime", 0)),
        "tenant_id": event.get("tenantId", "platform"),
        "request_id": event.get("correlationID", event.get("sessionId", "")),
    }
