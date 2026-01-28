# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Transformer configuration models with JSON Schema validation (CAB-881).

Config is inline in UAC per-tenant configuration:

    transform:
      fields:
        - id
        - title
        - status
      max_depth: 2
      max_items: 50
      truncate:
        description: { max: 500, strategy: "middle" }
        content: { max: 1000, strategy: "end" }
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator, model_validator


class TruncateStrategy(str, Enum):
    """How to truncate long text fields."""
    END = "end"        # Keep first N chars
    MIDDLE = "middle"  # Keep first_n + last_n, cut middle


class TruncateConfig(BaseModel):
    """Truncation config for a single field."""
    max: int = 500
    strategy: TruncateStrategy = TruncateStrategy.MIDDLE

    @field_validator("max")
    @classmethod
    def max_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max must be >= 1")
        return v


class TransformFieldConfig(BaseModel):
    """Config for field selection — which fields to keep."""
    fields: list[str] = []
    max_depth: int = 3
    max_items: int = 50
    truncate: dict[str, TruncateConfig] = {}

    @field_validator("max_depth")
    @classmethod
    def depth_range(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_depth must be between 1 and 10")
        return v

    @field_validator("max_items")
    @classmethod
    def items_range(cls, v: int) -> int:
        if v < 1 or v > 1000:
            raise ValueError("max_items must be between 1 and 1000")
        return v


class TransformConfig(BaseModel):
    """Top-level transform config for a tenant+tool pair.

    Validated via Pydantic (acts as JSON Schema validation).
    Invalid config is rejected at load time, never at request time.
    """
    enabled: bool = True
    fields: list[str] = []
    max_depth: int = 3
    max_items: int = 50
    truncate: dict[str, TruncateConfig] = {}

    @field_validator("max_depth")
    @classmethod
    def depth_range(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_depth must be between 1 and 10")
        return v

    @field_validator("max_items")
    @classmethod
    def items_range(cls, v: int) -> int:
        if v < 1 or v > 1000:
            raise ValueError("max_items must be between 1 and 1000")
        return v

    @model_validator(mode="after")
    def validate_truncate_fields(self) -> "TransformConfig":
        """Warn if truncate references fields not in the whitelist."""
        if self.fields and self.truncate:
            for field_name in self.truncate:
                if field_name not in self.fields:
                    # Not an error — truncate can target nested fields
                    # that aren't top-level whitelist entries
                    pass
        return self


# Default configs for known tools (used when tenant has no custom config).
# These are baseline defaults — adapters in adapters/ override with
# richer configs that include dot-notation fields and custom transforms.
# Kept here as fallback if adapters aren't loaded.
DEFAULT_CONFIGS: dict[str, TransformConfig] = {
    "linear": TransformConfig(
        fields=["id", "identifier", "title", "state.name", "state.type",
                "priority", "assignee.name", "project.name", "labels",
                "updatedAt", "url"],
        max_depth=2,
        max_items=25,
        truncate={
            "description": TruncateConfig(max=300, strategy=TruncateStrategy.MIDDLE),
        },
    ),
    "notion": TransformConfig(
        fields=["id", "title", "url", "type", "parent.type", "parent.title",
                "lastEditedTime", "createdBy.name", "properties", "status"],
        max_depth=3,
        max_items=20,
        truncate={
            "content": TruncateConfig(max=500, strategy=TruncateStrategy.MIDDLE),
            "rich_text": TruncateConfig(max=200, strategy=TruncateStrategy.END),
        },
    ),
}
