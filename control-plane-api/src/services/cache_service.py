# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""In-memory cache service with TTL support.

Provides a simple cache for high-frequency lookups like API key validation.
For multi-instance deployments, replace with Redis.

Performance optimization: CAB-PERF
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
from dataclasses import dataclass
from functools import wraps


@dataclass
class CacheEntry:
    """Cache entry with value and expiration time."""
    value: Any
    expires_at: datetime


class TTLCache:
    """Thread-safe in-memory cache with TTL expiration.

    Suitable for single-instance deployments. For multi-instance
    deployments, use Redis or similar distributed cache.
    """

    def __init__(self, default_ttl_seconds: int = 10, max_size: int = 10000):
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if exists and not expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if datetime.utcnow() > entry.expires_at:
                del self._cache[key]
                return None

            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)

        async with self._lock:
            # Evict oldest entries if cache is full
            if len(self._cache) >= self._max_size:
                await self._evict_expired()
                # If still full, remove oldest entries
                if len(self._cache) >= self._max_size:
                    oldest_keys = sorted(
                        self._cache.keys(),
                        key=lambda k: self._cache[k].expires_at
                    )[:len(self._cache) // 10]  # Remove 10%
                    for k in oldest_keys:
                        del self._cache[k]

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def _evict_expired(self) -> int:
        """Remove expired entries. Called internally with lock held."""
        now = datetime.utcnow()
        expired_keys = [
            k for k, v in self._cache.items()
            if now > v.expires_at
        ]
        for k in expired_keys:
            del self._cache[k]
        return len(expired_keys)

    async def clear(self) -> None:
        """Clear all entries from cache."""
        async with self._lock:
            self._cache.clear()

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "default_ttl": self._default_ttl,
        }


# Global cache instances
api_key_cache = TTLCache(default_ttl_seconds=10, max_size=10000)


def cached(cache: TTLCache, key_prefix: str, ttl_seconds: Optional[int] = None):
    """Decorator for caching async function results.

    Usage:
        @cached(api_key_cache, "apikey", ttl_seconds=10)
        async def validate_key(key_hash: str) -> dict:
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from prefix and first argument
            if args:
                cache_key = f"{key_prefix}:{args[0]}"
            else:
                # Use all kwargs values for key
                cache_key = f"{key_prefix}:{':'.join(str(v) for v in kwargs.values())}"

            # Try cache first
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                await cache.set(cache_key, result, ttl_seconds)

            return result
        return wrapper
    return decorator
