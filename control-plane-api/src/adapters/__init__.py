"""STOA Gateway Adapter Pattern — Bring Your Own Gateway.

This package defines the abstract interface for gateway orchestration
and provides concrete implementations for supported gateways.
"""

from .gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from .registry import AdapterRegistry

__all__ = ["AdapterRegistry", "AdapterResult", "GatewayAdapterInterface"]
