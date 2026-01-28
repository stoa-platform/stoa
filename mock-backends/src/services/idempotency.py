# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Idempotency store for Settlement API.

CAB-1018: Mock APIs for Central Bank Demo
In-memory idempotency store with TTL for demo purposes.

In production, this would use Redis with SETNX for atomic operations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class IdempotencyEntry:
    """Entry in the idempotency store."""

    key: str
    response: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    request_hash: Optional[str] = None  # For request body validation


class IdempotencyStore:
    """In-memory idempotency store with TTL.

    For demo purposes only. In production, use Redis with:
    - SETNX for atomic check-and-set
    - EXPIRE for automatic TTL
    - Distributed lock for concurrent requests

    Features:
    - check(key) → returns cached response if exists
    - save(key, response) → stores response with timestamp
    - cleanup() → removes expired entries
    - get_stats() → returns store statistics for /demo/state
    """

    def __init__(self, ttl_seconds: Optional[int] = None):
        self._store: dict[str, IdempotencyEntry] = {}
        self._ttl = timedelta(seconds=ttl_seconds or settings.idempotency_ttl_seconds)
        self._hits = 0
        self._misses = 0

    def check(self, key: str) -> Optional[Any]:
        """Check if idempotency key exists and is valid.

        Args:
            key: Idempotency key from header

        Returns:
            Cached response if exists and not expired, None otherwise
        """
        if key not in self._store:
            self._misses += 1
            logger.debug("Idempotency miss", key=key)
            return None

        entry = self._store[key]
        now = datetime.utcnow()

        # Check if expired
        if now - entry.created_at >= self._ttl:
            del self._store[key]
            self._misses += 1
            logger.debug("Idempotency expired", key=key)
            return None

        self._hits += 1
        logger.info(
            "Idempotency hit - returning cached response",
            key=key,
            age_seconds=(now - entry.created_at).total_seconds(),
        )
        return entry.response

    def save(self, key: str, response: Any, request_hash: Optional[str] = None) -> None:
        """Save response for idempotency key.

        Args:
            key: Idempotency key from header
            response: Response to cache
            request_hash: Optional hash of request body for validation
        """
        self._store[key] = IdempotencyEntry(
            key=key,
            response=response,
            created_at=datetime.utcnow(),
            request_hash=request_hash,
        )
        logger.info("Idempotency entry saved", key=key)

    def cleanup(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed
        """
        now = datetime.utcnow()
        expired_keys = [
            key
            for key, entry in self._store.items()
            if now - entry.created_at >= self._ttl
        ]

        for key in expired_keys:
            del self._store[key]

        if expired_keys:
            logger.info("Idempotency cleanup", removed_count=len(expired_keys))

        return len(expired_keys)

    def clear(self) -> int:
        """Clear all entries (for demo reset).

        Returns:
            Number of entries cleared
        """
        count = len(self._store)
        self._store.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Idempotency store cleared", cleared_count=count)
        return count

    def get_stats(self) -> dict:
        """Get store statistics for /demo/state.

        Returns:
            Statistics dict
        """
        now = datetime.utcnow()
        active_entries = [
            entry
            for entry in self._store.values()
            if now - entry.created_at < self._ttl
        ]

        return {
            "total_entries": len(self._store),
            "active_entries": len(active_entries),
            "ttl_seconds": self._ttl.total_seconds(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": self._hits / (self._hits + self._misses)
            if (self._hits + self._misses) > 0
            else 0.0,
        }


# Singleton instance
_idempotency_store: Optional[IdempotencyStore] = None


def get_idempotency_store() -> IdempotencyStore:
    """Get the singleton idempotency store instance."""
    global _idempotency_store
    if _idempotency_store is None:
        _idempotency_store = IdempotencyStore()
    return _idempotency_store
