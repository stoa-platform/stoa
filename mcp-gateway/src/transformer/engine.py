# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Transform Engine — field selection, truncation, pagination (CAB-881).

Core transformation logic. Stateless, operates on dicts.
"""

from __future__ import annotations

import copy
from typing import Any

from .config import TransformConfig, TruncateConfig, TruncateStrategy


class TransformEngine:
    """Stateless engine for applying transformations to MCP response payloads."""

    @staticmethod
    def apply(data: dict[str, Any], config: TransformConfig) -> dict[str, Any]:
        """Apply all transformations in order: fields → truncation → pagination."""
        if not config.enabled:
            return data

        result = data

        # 1. Field selection (whitelist)
        if config.fields:
            result = TransformEngine.select_fields(result, config.fields, config.max_depth)

        # 2. Truncation
        if config.truncate:
            result = TransformEngine.truncate_fields(result, config.truncate)

        # 3. Pagination (auto-detect arrays)
        result = TransformEngine.paginate_arrays(result, config.max_items)

        return result

    @staticmethod
    def select_fields(
        data: Any,
        fields: list[str],
        max_depth: int,
        _depth: int = 0,
    ) -> Any:
        """Select only whitelisted fields from a dict (recursive).

        Supports dot-notation for nested fields: "assignee.name" keeps
        only the "name" key inside the "assignee" object.

        Args:
            data: The data to filter.
            fields: Whitelist of field names (supports dot notation).
            max_depth: Maximum recursion depth.
            _depth: Current recursion depth (internal).
        """
        if _depth >= max_depth:
            return data

        if isinstance(data, dict):
            # Split fields into top-level and nested
            top_level: set[str] = set()
            nested: dict[str, list[str]] = {}

            for f in fields:
                if "." in f:
                    parent, child = f.split(".", 1)
                    top_level.add(parent)
                    nested.setdefault(parent, []).append(child)
                else:
                    top_level.add(f)

            result = {}
            for key in data:
                if key not in top_level:
                    continue
                value = data[key]
                if key in nested:
                    # Recurse into nested fields
                    result[key] = TransformEngine.select_fields(
                        value, nested[key], max_depth, _depth + 1
                    )
                else:
                    result[key] = value

            return result

        if isinstance(data, list):
            return [
                TransformEngine.select_fields(item, fields, max_depth, _depth)
                for item in data
            ]

        return data

    @staticmethod
    def truncate_fields(
        data: Any,
        truncate_configs: dict[str, TruncateConfig],
    ) -> Any:
        """Apply truncation to specified fields."""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if key in truncate_configs and isinstance(value, str):
                    result[key] = TransformEngine.truncate_text(
                        value, truncate_configs[key]
                    )
                elif isinstance(value, (dict, list)):
                    result[key] = TransformEngine.truncate_fields(
                        value, truncate_configs
                    )
                else:
                    result[key] = value
            return result

        if isinstance(data, list):
            return [
                TransformEngine.truncate_fields(item, truncate_configs)
                for item in data
            ]

        return data

    @staticmethod
    def truncate_text(text: str, config: TruncateConfig) -> str:
        """Truncate a text string according to the configured strategy.

        Strategies:
        - end: Keep first `max` chars, append marker.
        - middle: Keep first half + last half, cut middle with marker.
        """
        if len(text) <= config.max:
            return text

        removed = len(text) - config.max
        marker = f"[...truncated {removed} chars...]"

        if config.strategy == TruncateStrategy.END:
            return text[:config.max] + marker

        # MIDDLE strategy: keep first_n + last_n
        keep = config.max - len(marker)
        if keep <= 0:
            return text[:config.max] + marker

        first_n = keep // 2
        last_n = keep - first_n
        if last_n > 0:
            return text[:first_n] + marker + text[-last_n:]
        return text[:first_n] + marker

    @staticmethod
    def paginate_arrays(
        data: Any,
        max_items: int,
    ) -> Any:
        """Auto-paginate arrays that exceed max_items.

        Replaces large arrays with:
        {
            "items": [...truncated array...],
            "_pagination": { "total": N, "returned": M, "has_more": true }
        }
        """
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if isinstance(value, list) and len(value) > max_items:
                    result[key] = {
                        "items": value[:max_items],
                        "_pagination": {
                            "total": len(value),
                            "returned": max_items,
                            "has_more": True,
                        },
                    }
                elif isinstance(value, (dict, list)):
                    result[key] = TransformEngine.paginate_arrays(value, max_items)
                else:
                    result[key] = value
            return result

        if isinstance(data, list):
            if len(data) > max_items:
                return {
                    "items": [
                        TransformEngine.paginate_arrays(item, max_items)
                        for item in data[:max_items]
                    ],
                    "_pagination": {
                        "total": len(data),
                        "returned": max_items,
                        "has_more": True,
                    },
                }
            return [
                TransformEngine.paginate_arrays(item, max_items)
                for item in data
            ]

        return data
