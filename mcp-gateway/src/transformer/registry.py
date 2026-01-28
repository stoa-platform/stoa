# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Adapter registry — maps tool names to TransformerAdapter instances (CAB-881).

Resolution priority for configs:
1. Tenant-specific config (from UAC)
2. Registered adapter's default config (if adapter has get_default_config())
3. DEFAULT_CONFIGS fallback (from config.py)
4. None (no transformation)
"""

from __future__ import annotations

from .base import TransformerAdapter
from .config import TransformConfig, DEFAULT_CONFIGS


class _DefaultAdapter(TransformerAdapter):
    """Fallback adapter with no default fields (passes through)."""

    def get_default_fields(self) -> list[str]:
        return []

    def get_tool_prefix(self) -> str:
        return ""


_default_adapter = _DefaultAdapter()

# Registry: prefix → adapter instance
_adapters: dict[str, TransformerAdapter] = {}


def register_adapter(adapter: TransformerAdapter) -> None:
    """Register a TransformerAdapter by its prefix."""
    _adapters[adapter.get_tool_prefix()] = adapter


def get_adapter(tool_name: str) -> TransformerAdapter:
    """Find the adapter matching a tool_name by prefix.

    E.g., tool_name="linear-list-issues" matches adapter with prefix="linear".
    Falls back to _default_adapter if no match.
    """
    for prefix, adapter in _adapters.items():
        if tool_name.startswith(prefix):
            return adapter
    return _default_adapter


def get_config_for_tool(
    tool_name: str,
    tenant_config: dict[str, TransformConfig] | None = None,
) -> TransformConfig | None:
    """Resolve the TransformConfig for a given tool.

    Priority:
    1. Tenant-specific config (from UAC)
    2. Registered adapter's config (adapter.get_default_config())
    3. DEFAULT_CONFIGS fallback
    4. None (no transformation)
    """
    # 1. Check tenant config first
    if tenant_config:
        for prefix, config in tenant_config.items():
            if tool_name.startswith(prefix):
                return config

    # 2. Check registered adapter
    for prefix, adapter in _adapters.items():
        if tool_name.startswith(prefix):
            if hasattr(adapter, "get_default_config"):
                return adapter.get_default_config()

    # 3. Check built-in defaults
    for prefix, config in DEFAULT_CONFIGS.items():
        if tool_name.startswith(prefix):
            return config

    return None


def get_registered_adapters() -> dict[str, TransformerAdapter]:
    """Return all registered adapters (for introspection/testing)."""
    return dict(_adapters)
