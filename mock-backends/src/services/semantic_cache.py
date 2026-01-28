# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Semantic cache for Sanctions Screening API.

CAB-1018: Mock APIs for Central Bank Demo
Simple normalized key-based cache (not fuzzy matching per Council feedback).

Cache key = normalize(entity_name) + entity_type + country
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)


def normalize(name: str) -> str:
    """Normalize entity name for cache key generation.

    Council feedback (Archi 50x50): Simple normalize().lower(), no fuzzy matching.

    Normalization:
    - Strip whitespace
    - Convert to lowercase
    - Replace hyphens with spaces
    - Collapse multiple spaces

    Args:
        name: Entity name to normalize

    Returns:
        Normalized name
    """
    normalized = name.strip().lower()
    normalized = normalized.replace("-", " ")
    normalized = " ".join(normalized.split())  # Collapse multiple spaces
    return normalized


def generate_cache_key(entity_name: str, entity_type: str, country: str) -> str:
    """Generate cache key from entity attributes.

    Args:
        entity_name: Entity name (will be normalized)
        entity_type: Entity type (PERSON/ORGANIZATION)
        country: Country code

    Returns:
        Cache key string
    """
    normalized_name = normalize(entity_name)
    key_source = f"{normalized_name}|{entity_type.upper()}|{country.upper()}"
    return hashlib.sha256(key_source.encode()).hexdigest()[:16]


@dataclass
class CacheEntry:
    """Entry in the semantic cache."""

    key: str
    response: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    normalized_name: str = ""


class SemanticCache:
    """Simple semantic cache for sanctions screening.

    Uses normalized entity names as cache keys.
    NOT fuzzy matching - exact normalized match only.

    Features:
    - normalize(name) → simple normalization
    - get(key) → cached response or None
    - set(key, response) → stores with TTL
    - clear() → for demo reset
    - get_stats() → for /demo/state
    """

    def __init__(self, ttl_seconds: Optional[int] = None):
        self._cache: dict[str, CacheEntry] = {}
        self._ttl = timedelta(seconds=ttl_seconds or settings.semantic_cache_ttl_seconds)
        self._hits = 0
        self._misses = 0

    def get(self, entity_name: str, entity_type: str, country: str) -> Optional[Any]:
        """Get cached response for entity.

        Args:
            entity_name: Entity name
            entity_type: Entity type
            country: Country code

        Returns:
            Cached response if exists and not expired, None otherwise
        """
        key = generate_cache_key(entity_name, entity_type, country)

        if key not in self._cache:
            self._misses += 1
            logger.debug(
                "Semantic cache miss",
                entity_name=entity_name,
                normalized=normalize(entity_name),
            )
            return None

        entry = self._cache[key]
        now = datetime.utcnow()

        # Check if expired
        if now - entry.created_at >= self._ttl:
            del self._cache[key]
            self._misses += 1
            logger.debug("Semantic cache expired", key=key)
            return None

        self._hits += 1
        logger.info(
            "Semantic cache hit",
            entity_name=entity_name,
            normalized=normalize(entity_name),
            age_seconds=(now - entry.created_at).total_seconds(),
        )
        return entry.response

    def set(
        self, entity_name: str, entity_type: str, country: str, response: Any
    ) -> str:
        """Cache response for entity.

        Args:
            entity_name: Entity name
            entity_type: Entity type
            country: Country code
            response: Response to cache

        Returns:
            Cache key used
        """
        key = generate_cache_key(entity_name, entity_type, country)
        normalized_name = normalize(entity_name)

        self._cache[key] = CacheEntry(
            key=key,
            response=response,
            created_at=datetime.utcnow(),
            normalized_name=normalized_name,
        )

        logger.info(
            "Semantic cache entry stored",
            key=key,
            normalized_name=normalized_name,
        )
        return key

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Semantic cache cleared", cleared_count=count)
        return count

    def cleanup(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed
        """
        now = datetime.utcnow()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if now - entry.created_at >= self._ttl
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info("Semantic cache cleanup", removed_count=len(expired_keys))

        return len(expired_keys)

    def get_stats(self) -> dict:
        """Get cache statistics for /demo/state.

        Returns:
            Statistics dict
        """
        now = datetime.utcnow()
        active_entries = [
            entry
            for entry in self._cache.values()
            if now - entry.created_at < self._ttl
        ]

        total_requests = self._hits + self._misses

        return {
            "total_entries": len(self._cache),
            "active_entries": len(active_entries),
            "ttl_seconds": self._ttl.total_seconds(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": self._hits / total_requests if total_requests > 0 else 0.0,
        }


# Singleton instance
_semantic_cache: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    """Get the singleton semantic cache instance."""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCache()
    return _semantic_cache
