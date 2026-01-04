"""Metering event models for STOA MCP Gateway.

Defines the schema for metering events that are sent to Kafka
for usage tracking, billing, and analytics.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MeteringStatus(str, Enum):
    """Status of a metered operation."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAUTHORIZED = "unauthorized"


class MeteringEvent(BaseModel):
    """Metering event for usage tracking.

    This event is emitted after each tool invocation and sent to Kafka
    for aggregation by ksqlDB and storage in TimescaleDB.

    Attributes:
        event_id: Unique identifier for this event
        timestamp: When the event occurred (ISO 8601)
        tenant: Tenant identifier (e.g., "acme-corp")
        project: Project or API identifier
        consumer: Consumer identifier (e.g., "claude-desktop", "cursor")
        user_id: Authenticated user's subject claim
        tool: Tool name that was invoked
        latency_ms: Execution time in milliseconds
        status: Outcome of the operation
        cost_units: Computed cost units for billing
        request_id: Correlation ID for tracing
        metadata: Additional context (arguments, errors, etc.)
    """

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    event_id: UUID = Field(default_factory=uuid4, description="Unique event ID")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event timestamp in UTC",
    )
    tenant: str = Field(..., description="Tenant identifier", min_length=1, max_length=64)
    project: str | None = Field(None, description="Project or API identifier")
    consumer: str = Field(
        default="unknown",
        description="Consumer application (claude-desktop, cursor, etc.)",
    )
    user_id: str = Field(..., description="User subject claim", min_length=1)
    tool: str = Field(..., description="Tool name", min_length=1, max_length=128)
    latency_ms: int = Field(..., ge=0, description="Execution latency in milliseconds")
    status: MeteringStatus = Field(..., description="Operation status")
    cost_units: float = Field(
        default=0.001,
        ge=0.0,
        description="Cost units for billing",
    )
    request_id: str | None = Field(None, description="Request correlation ID")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    def to_kafka_message(self) -> dict[str, Any]:
        """Convert to Kafka message format.

        Returns:
            Dictionary suitable for JSON serialization to Kafka.
        """
        return {
            "event_id": str(self.event_id),
            "timestamp": self.timestamp.isoformat() + "Z",
            "tenant": self.tenant,
            "project": self.project,
            "consumer": self.consumer,
            "user_id": self.user_id,
            "tool": self.tool,
            "latency_ms": self.latency_ms,
            "status": self.status.value,
            "cost_units": self.cost_units,
            "request_id": self.request_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_tool_invocation(
        cls,
        tenant: str,
        user_id: str,
        tool: str,
        latency_ms: int,
        status: MeteringStatus,
        *,
        project: str | None = None,
        consumer: str = "unknown",
        request_id: str | None = None,
        cost_units: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "MeteringEvent":
        """Create a metering event from tool invocation context.

        Args:
            tenant: Tenant identifier
            user_id: User's subject claim
            tool: Tool name
            latency_ms: Execution time
            status: Operation outcome
            project: Optional project identifier
            consumer: Consumer application name
            request_id: Optional correlation ID
            cost_units: Optional cost override (default 0.001)
            metadata: Optional additional context

        Returns:
            A new MeteringEvent instance.
        """
        return cls(
            tenant=tenant,
            project=project,
            consumer=consumer,
            user_id=user_id,
            tool=tool,
            latency_ms=latency_ms,
            status=status,
            cost_units=cost_units if cost_units is not None else cls._compute_cost(tool, latency_ms),
            request_id=request_id,
            metadata=metadata or {},
        )

    @staticmethod
    def _compute_cost(tool: str, latency_ms: int) -> float:
        """Compute cost units based on tool and latency.

        Default pricing model:
        - Base cost: 0.001 per call
        - Additional cost for longer executions
        - Premium tools have higher cost

        Args:
            tool: Tool name
            latency_ms: Execution time

        Returns:
            Cost units as a float.
        """
        base_cost = 0.001

        # Add latency-based cost (0.0001 per 100ms)
        latency_cost = (latency_ms / 100) * 0.0001

        # Premium tools (destructive operations)
        premium_tools = {"stoa_delete_api", "stoa_delete_tool", "stoa_deploy_api"}
        if tool in premium_tools:
            base_cost *= 2

        return round(base_cost + latency_cost, 6)


class MeteringEventBatch(BaseModel):
    """Batch of metering events for bulk processing."""

    events: list[MeteringEvent] = Field(..., description="List of events")
    batch_id: UUID = Field(default_factory=uuid4, description="Batch identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def count(self) -> int:
        """Number of events in the batch."""
        return len(self.events)

    @property
    def total_cost_units(self) -> float:
        """Total cost units across all events."""
        return sum(e.cost_units for e in self.events)
