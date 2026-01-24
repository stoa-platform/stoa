"""Metering module for STOA MCP Gateway.

This module provides usage metering for billing and analytics:
- Event schema for metering data
- Kafka producer for event streaming
- Middleware for automatic metering
"""

from .models import (
    MeteringEvent,
    MeteringStatus,
    MeteringEventBatch,
)
from .producer import (
    MeteringProducer,
    get_metering_producer,
    shutdown_metering_producer,
)

__all__ = [
    # Models
    "MeteringEvent",
    "MeteringStatus",
    "MeteringEventBatch",
    # Producer
    "MeteringProducer",
    "get_metering_producer",
    "shutdown_metering_producer",
]
