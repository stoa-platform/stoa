# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tool registry data models.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-605 Phase 3: Deprecation layer models.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class DeprecatedToolAlias:
    """Alias for backward compatibility during deprecation period.

    CAB-605: When old tools are renamed/consolidated, aliases allow
    existing clients to continue working for 60 days with warnings.

    Attributes:
        old_name: The deprecated tool name
        new_name: The replacement tool name
        new_args: Arguments to inject when redirecting
        deprecated_at: When the deprecation started
        remove_after: When the alias will stop working (60 days default)
    """

    old_name: str
    new_name: str
    new_args: dict[str, Any] = field(default_factory=dict)
    deprecated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    remove_after: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=60)
    )

    def is_expired(self) -> bool:
        """Check if the deprecation period has ended."""
        return datetime.now(timezone.utc) > self.remove_after

    def days_until_removal(self) -> int:
        """Get days remaining until removal."""
        remaining = self.remove_after - datetime.now(timezone.utc)
        return max(0, remaining.days)
