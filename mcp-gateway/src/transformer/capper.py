# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Response Capping Engine — Token-aware truncation (CAB-874).

Caps MCP response payloads to a maximum token budget using smart strategies:
- JSON arrays: Binary search to find max items that fit
- Objects with list values: Cap the largest list
- Plain text: Character-level truncation

Runs AFTER TransformEngine (field selection, truncation, pagination).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..middleware.token_counter import count_tokens


@dataclass
class CapResult:
    """Result of a capping operation."""

    payload: Any
    was_capped: bool
    original_tokens: int
    final_tokens: int
    items_kept: int | None = None
    total_items: int | None = None


def _serialize(payload: Any) -> str:
    """Compact JSON serialization."""
    return json.dumps(payload, separators=(",", ":"))


def _create_marker(
    original_tokens: int,
    final_tokens: int,
    items_kept: int | None = None,
    total_items: int | None = None,
) -> str:
    """Create inline truncation marker visible to AI agents."""
    if items_kept is not None and total_items is not None:
        return (
            f"\n\n[STOA: Response truncated from {original_tokens} "
            f"to {final_tokens} tokens. "
            f"Showing {items_kept}/{total_items} items.]"
        )
    return (
        f"\n\n[STOA: Response truncated from {original_tokens} "
        f"to {final_tokens} tokens.]"
    )


class CapEngine:
    """Stateless token-aware response capping engine."""

    MARKER_RESERVE = 200  # tokens reserved for the inline marker

    @staticmethod
    def cap_response(
        payload: Any,
        max_tokens: int,
        tool_name: str = "unknown",
    ) -> CapResult:
        """Cap a response payload to fit within max_tokens.

        Strategy:
        1. If under budget, return as-is.
        2. If payload is a list, binary-search for max items.
        3. If payload is a dict with a list value, cap the largest list.
        4. Otherwise, character-level truncation.
        """
        serialized = _serialize(payload)
        original_tokens = count_tokens(serialized)

        if original_tokens <= max_tokens:
            return CapResult(
                payload=payload,
                was_capped=False,
                original_tokens=original_tokens,
                final_tokens=original_tokens,
            )

        target = max_tokens - CapEngine.MARKER_RESERVE

        # Strategy 1: Top-level list
        if isinstance(payload, list):
            return CapEngine._cap_array(payload, target, original_tokens)

        # Strategy 2: Dict with a list value (e.g. {"issues": [...], ...})
        if isinstance(payload, dict):
            best_key = None
            best_len = 0
            for k, v in payload.items():
                if isinstance(v, list) and len(v) > best_len:
                    best_key = k
                    best_len = len(v)

            if best_key is not None and best_len > 0:
                return CapEngine._cap_dict_list(
                    payload, best_key, target, original_tokens
                )

        # Strategy 3: Character-level truncation of serialized JSON
        return CapEngine._cap_text(serialized, target, original_tokens)

    @staticmethod
    def _cap_array(
        array: list,
        target_tokens: int,
        original_tokens: int,
    ) -> CapResult:
        """Binary search for max items fitting in token budget."""
        total = len(array)
        lo, hi = 0, total
        best = 0

        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = _serialize(array[:mid])
            if count_tokens(candidate) <= target_tokens:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        kept = array[:best]
        final_str = _serialize(kept)
        final_tokens = count_tokens(final_str)
        marker = _create_marker(original_tokens, final_tokens, best, total)

        # Append marker as last element for JSON arrays
        kept.append(marker)

        return CapResult(
            payload=kept,
            was_capped=True,
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            items_kept=best,
            total_items=total,
        )

    @staticmethod
    def _cap_dict_list(
        data: dict,
        list_key: str,
        target_tokens: int,
        original_tokens: int,
    ) -> CapResult:
        """Cap the largest list inside a dict."""
        array = data[list_key]
        total = len(array)

        lo, hi = 0, total
        best = 0

        while lo <= hi:
            mid = (lo + hi) // 2
            candidate_dict = {**data, list_key: array[:mid]}
            candidate = _serialize(candidate_dict)
            if count_tokens(candidate) <= target_tokens:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        capped_dict = {**data, list_key: array[:best]}
        final_str = _serialize(capped_dict)
        final_tokens = count_tokens(final_str)
        marker = _create_marker(original_tokens, final_tokens, best, total)

        # Append marker to the list
        capped_dict[list_key].append(marker)

        return CapResult(
            payload=capped_dict,
            was_capped=True,
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            items_kept=best,
            total_items=total,
        )

    @staticmethod
    def _cap_text(
        text: str,
        target_tokens: int,
        original_tokens: int,
    ) -> CapResult:
        """Character-level truncation for non-structured payloads."""
        # Approximate: 1 token ≈ 4 chars
        char_limit = target_tokens * 4
        truncated = text[:char_limit]

        # Iteratively shrink if still over budget
        while count_tokens(truncated) > target_tokens and len(truncated) > 100:
            truncated = truncated[: int(len(truncated) * 0.9)]

        final_tokens = count_tokens(truncated)
        marker = _create_marker(original_tokens, final_tokens)
        result_text = truncated + marker

        return CapResult(
            payload=result_text,
            was_capped=True,
            original_tokens=original_tokens,
            final_tokens=final_tokens,
        )
