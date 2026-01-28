# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Response Transformer — CAB-881.

Reduces MCP response payloads via field selection, truncation,
and automatic pagination. Configurable per-tenant via UAC inline config.

Importing this module auto-registers all built-in adapters
(Linear Lite, Notion Lite).
"""

from .config import TransformConfig, TruncateConfig, TransformFieldConfig
from .engine import TransformEngine
from .base import TransformerAdapter

# Auto-register built-in adapters on import
from . import adapters as _adapters  # noqa: F401

__all__ = [
    "TransformConfig",
    "TruncateConfig",
    "TransformFieldConfig",
    "TransformEngine",
    "TransformerAdapter",
]
