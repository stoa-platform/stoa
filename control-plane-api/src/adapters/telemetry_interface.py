"""Abstract Telemetry Adapter Interface for STOA Platform.

Defines the contract for collecting observability data (logs, metrics)
from any API gateway. Separate from GatewayAdapterInterface to keep
the 16-method orchestration contract clean.

Two collection strategies:
1. Pull: periodic polling via get_access_logs() / get_metrics_snapshot()
2. Push: gateway pushes events to webhook via setup_push_subscription()

See CAB-1681 for architectural context.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from .gateway_adapter_interface import AdapterResult


class TelemetryAdapterInterface(ABC):
    """Abstract interface for gateway telemetry collection.

    Implementations collect access logs and metrics from a specific
    gateway type. All methods are non-blocking — failures are logged
    as warnings and never crash the caller.
    """

    @abstractmethod
    async def get_access_logs(self, since: datetime, limit: int = 1000) -> list[dict]:
        """Pull access logs from the gateway since a given timestamp.

        Args:
            since: Only return logs after this timestamp.
            limit: Maximum number of log entries to return.

        Returns:
            List of normalized log entries with common schema fields:
            {timestamp, gateway_type, gateway_id, tenant_id, method,
             path, status, latency_ms, request_id, trace_id}
        """
        ...

    @abstractmethod
    async def get_metrics_snapshot(self) -> dict:
        """Pull a point-in-time metrics snapshot from the gateway.

        Returns:
            Dict with gateway-specific metrics (request counts,
            error rates, latency percentiles, connection pool stats).
        """
        ...

    @abstractmethod
    async def setup_push_subscription(self, webhook_url: str) -> AdapterResult:
        """Configure the gateway to push telemetry events to a webhook.

        Args:
            webhook_url: URL where the gateway should POST log events.

        Returns:
            AdapterResult indicating success/failure of subscription setup.
            Not all gateways support push — unsupported returns
            AdapterResult(success=False, error="Push not supported").
        """
        ...
