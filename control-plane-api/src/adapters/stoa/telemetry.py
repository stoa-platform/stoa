"""STOA Gateway telemetry adapter.

STOA Gateway emits OTLP directly to Alloy, so access logs are not
pulled from the gateway itself (Fluent-Bit handles that). The metrics
snapshot scrapes the Prometheus /metrics endpoint.

See CAB-1683 for context.
"""

import logging
from datetime import datetime

import httpx

from ..gateway_adapter_interface import AdapterResult
from ..telemetry_interface import TelemetryAdapterInterface

logger = logging.getLogger(__name__)


class StoaTelemetryAdapter(TelemetryAdapterInterface):
    """STOA Gateway telemetry — metrics via /metrics, logs via Fluent-Bit."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._base_url = self._config.get("base_url", "http://localhost:8080")
        auth_config = self._config.get("auth_config", {})
        self._admin_token = auth_config.get("admin_token", "") if isinstance(auth_config, dict) else ""

    async def get_access_logs(self, since: datetime, limit: int = 1000) -> list[dict]:
        """STOA Gateway logs are collected by Fluent-Bit, not pulled."""
        return []

    async def get_metrics_snapshot(self) -> dict:
        """Scrape /metrics endpoint (Prometheus text format) and return key counters."""
        try:
            headers: dict[str, str] = {}
            if self._admin_token:
                headers["Authorization"] = f"Bearer {self._admin_token}"
            async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
                resp = await client.get("/metrics", headers=headers)
                if resp.status_code == 200:
                    return _parse_prometheus_text(resp.text)
                return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning("STOA metrics scrape failed: %s", e)
            return {"error": str(e)}

    async def setup_push_subscription(self, webhook_url: str) -> AdapterResult:
        """STOA Gateway pushes OTLP natively — no webhook setup needed."""
        return AdapterResult(
            success=True,
            data={"message": "STOA Gateway uses native OTLP push, no subscription needed"},
        )


def _parse_prometheus_text(text: str) -> dict:
    """Extract key metrics from Prometheus text exposition format."""
    metrics: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                metrics[parts[0]] = float(parts[1])
            except ValueError:
                continue
    return metrics
