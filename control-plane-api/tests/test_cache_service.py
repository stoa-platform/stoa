"""Tests for cache service — TTLCache with async operations."""

import asyncio

import pytest

from src.services.cache_service import TTLCache, cached


@pytest.fixture
def cache():
    return TTLCache(default_ttl_seconds=10, max_size=100)


class TestSetAndGet:
    async def test_set_get_returns_value(self, cache):
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    async def test_get_missing_returns_none(self, cache):
        result = await cache.get("nonexistent")
        assert result is None

    async def test_set_overwrites(self, cache):
        await cache.set("key1", "v1")
        await cache.set("key1", "v2")
        assert await cache.get("key1") == "v2"


class TestTTLExpiration:
    async def test_expired_returns_none(self, cache):
        await cache.set("key1", "value1", ttl_seconds=0)
        # Sleep briefly to ensure expiration
        await asyncio.sleep(0.01)
        result = await cache.get("key1")
        assert result is None


class TestDelete:
    async def test_delete_existing(self, cache):
        await cache.set("key1", "value1")
        result = await cache.delete("key1")
        assert result is True
        assert await cache.get("key1") is None

    async def test_delete_nonexistent(self, cache):
        result = await cache.delete("nonexistent")
        assert result is False


class TestDeleteByPrefix:
    async def test_deletes_matching_keys(self, cache):
        await cache.set("user:1", "a")
        await cache.set("user:2", "b")
        await cache.set("tenant:1", "c")
        count = await cache.delete_by_prefix("user:")
        assert count == 2
        assert await cache.get("user:1") is None
        assert await cache.get("tenant:1") == "c"


class TestClear:
    async def test_clear_empties_cache(self, cache):
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None


class TestStats:
    async def test_stats_returns_correct_counts(self, cache):
        await cache.set("a", 1)
        await cache.set("b", 2)
        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["default_ttl"] == 10


class TestEviction:
    async def test_evicts_when_full(self):
        # Use max_size=20 so 10% = 2 entries removed per eviction cycle
        small_cache = TTLCache(default_ttl_seconds=10, max_size=20)
        for i in range(40):
            await small_cache.set(f"key{i}", f"val{i}")
        # Cache should not grow unbounded
        assert small_cache.stats()["size"] <= 20


class TestCachedDecorator:
    async def test_cache_hit_avoids_call(self):
        call_count = 0
        test_cache = TTLCache(default_ttl_seconds=10, max_size=100)

        @cached(test_cache, "test", ttl_seconds=10)
        async def expensive_fn(key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result-{key}"

        r1 = await expensive_fn("abc")
        r2 = await expensive_fn("abc")
        assert r1 == r2 == "result-abc"
        assert call_count == 1

    async def test_cache_miss_calls_function(self):
        call_count = 0
        test_cache = TTLCache(default_ttl_seconds=10, max_size=100)

        @cached(test_cache, "test2", ttl_seconds=10)
        async def fn(key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"r-{key}"

        await fn("a")
        await fn("b")
        assert call_count == 2
