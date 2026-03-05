"""Telemetry Adapter Registry — Factory for telemetry adapters.

Separate from AdapterRegistry (gateway orchestration) to keep concerns
decoupled. Telemetry adapters are registered per gateway type.

See CAB-1682 for architectural context.
"""

import logging

from .telemetry_interface import TelemetryAdapterInterface

logger = logging.getLogger(__name__)


class TelemetryAdapterRegistry:
    """Factory for creating telemetry adapter instances by gateway type."""

    _adapters: dict[str, type[TelemetryAdapterInterface]] = {}

    @classmethod
    def register(cls, gateway_type: str, adapter_class: type[TelemetryAdapterInterface]) -> None:
        cls._adapters[gateway_type] = adapter_class
        logger.info("Registered telemetry adapter: %s -> %s", gateway_type, adapter_class.__name__)

    @classmethod
    def create(cls, gateway_type: str, config: dict | None = None) -> TelemetryAdapterInterface:
        adapter_class = cls._adapters.get(gateway_type)
        if not adapter_class:
            available = ", ".join(cls._adapters.keys()) or "(none)"
            raise ValueError(f"No telemetry adapter for '{gateway_type}'. Available: {available}")
        return adapter_class(config=config or {})

    @classmethod
    def has_type(cls, gateway_type: str) -> bool:
        return gateway_type in cls._adapters

    @classmethod
    def list_types(cls) -> list[str]:
        return list(cls._adapters.keys())


def register_default_adapters() -> None:
    """Register all built-in telemetry adapters."""
    from .gravitee.telemetry import GraviteeTelemetryAdapter
    from .kong.telemetry import KongTelemetryAdapter
    from .stoa.telemetry import StoaTelemetryAdapter
    from .webmethods.telemetry import WebMethodsTelemetryAdapter

    TelemetryAdapterRegistry.register("stoa", StoaTelemetryAdapter)
    TelemetryAdapterRegistry.register("kong", KongTelemetryAdapter)
    TelemetryAdapterRegistry.register("gravitee", GraviteeTelemetryAdapter)
    TelemetryAdapterRegistry.register("webmethods", WebMethodsTelemetryAdapter)
