# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Transformer Adapters — CAB-881 Step 3/4.

Auto-registers all adapters on import.
Import this module to populate the adapter registry.
"""

from .linear import LinearLiteAdapter
from .notion import NotionLiteAdapter
from ..registry import register_adapter

# Auto-register adapters
register_adapter(LinearLiteAdapter())
register_adapter(NotionLiteAdapter())

__all__ = [
    "LinearLiteAdapter",
    "NotionLiteAdapter",
]
