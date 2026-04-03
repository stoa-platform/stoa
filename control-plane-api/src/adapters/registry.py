"""Adapter Registry — Factory for creating gateway adapter instances.

Maintains a mapping of gateway_type -> adapter_class and creates
configured adapter instances on demand. Adapters are registered at
module load time (built-in) or dynamically (future plugin system).
"""

import logging

from .gateway_adapter_interface import GatewayAdapterInterface
from .metrics import InstrumentedAdapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Factory for creating gateway adapter instances by type."""

    _adapters: dict[str, type[GatewayAdapterInterface]] = {}

    @classmethod
    def register(cls, gateway_type: str, adapter_class: type[GatewayAdapterInterface]) -> None:
        """Register an adapter class for a gateway type.

        Args:
            gateway_type: Gateway type identifier (e.g. "webmethods", "kong")
            adapter_class: Class implementing GatewayAdapterInterface
        """
        cls._adapters[gateway_type] = adapter_class
        logger.info("Registered gateway adapter: %s -> %s", gateway_type, adapter_class.__name__)

    @classmethod
    def create(
        cls, gateway_type: str, config: dict | None = None, *, instrument: bool = True
    ) -> GatewayAdapterInterface:
        """Create an adapter instance for the given gateway type.

        Args:
            gateway_type: Gateway type identifier
            config: Connection configuration (base_url, auth_config, etc.)
            instrument: Wrap with InstrumentedAdapter for Prometheus metrics (default: True)

        Returns:
            Configured adapter instance (instrumented by default)

        Raises:
            ValueError: If no adapter is registered for the given type
        """
        adapter_class = cls._adapters.get(gateway_type)
        if not adapter_class:
            available = ", ".join(cls._adapters.keys()) or "(none)"
            raise ValueError(
                f"No adapter registered for gateway type '{gateway_type}'. " f"Available types: {available}"
            )
        adapter = adapter_class(config=config)
        if instrument:
            return InstrumentedAdapter(inner=adapter, gateway_type=gateway_type)
        return adapter

    @classmethod
    def list_types(cls) -> list[str]:
        """Return all registered gateway type identifiers."""
        return list(cls._adapters.keys())

    @classmethod
    def has_type(cls, gateway_type: str) -> bool:
        """Check if an adapter is registered for the given type."""
        return gateway_type in cls._adapters


def _register_builtin_adapters() -> None:
    """Register all built-in adapters. Called at module import time."""
    from .webmethods import WebMethodsGatewayAdapter

    AdapterRegistry.register("webmethods", WebMethodsGatewayAdapter)

    from .stoa import StoaGatewayAdapter

    AdapterRegistry.register("stoa", StoaGatewayAdapter)
    # STOA Gateway mode variants (ADR-024) — all use the same adapter
    AdapterRegistry.register("stoa_edge_mcp", StoaGatewayAdapter)
    AdapterRegistry.register("stoa_sidecar", StoaGatewayAdapter)
    AdapterRegistry.register("stoa_proxy", StoaGatewayAdapter)
    AdapterRegistry.register("stoa_shadow", StoaGatewayAdapter)

    from .kong import KongGatewayAdapter

    AdapterRegistry.register("kong", KongGatewayAdapter)

    from .gravitee import GraviteeGatewayAdapter

    AdapterRegistry.register("gravitee", GraviteeGatewayAdapter)

    from .apigee import ApigeeGatewayAdapter

    AdapterRegistry.register("apigee", ApigeeGatewayAdapter)

    from .aws import AwsApiGatewayAdapter

    AdapterRegistry.register("aws_apigateway", AwsApiGatewayAdapter)

    from .azure import AzureApimAdapter

    AdapterRegistry.register("azure_apim", AzureApimAdapter)


_register_builtin_adapters()
