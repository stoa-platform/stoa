# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Semantic Cache — CAB-881 Step 4/4.

Two-path lookup:
1. Fast path: SHA-256 exact match on (tenant_id, key_hash)
2. Semantic path: pgvector cosine similarity ≥ 0.95

Strict tenant isolation via WHERE clause on tenant_id.
TTL: 5 minutes (configurable).
"""

import json
from datetime import datetime, timezone, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .embedder import Embedder

logger = structlog.get_logger(__name__)

DEFAULT_TTL_SECONDS = 300  # 5 minutes
SIMILARITY_THRESHOLD = 0.95


class SemanticCache:
    """Embedding-based semantic cache with pgvector."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> None:
        self._embedder = embedder or Embedder()
        self._ttl_seconds = ttl_seconds
        self._similarity = similarity_threshold

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    async def lookup(
        self,
        session: AsyncSession,
        tenant_id: str,
        tool_name: str,
        arguments: dict,
    ) -> dict | None:
        """Look up a cached response.

        Returns the cached response dict, or None on miss.
        Uses fast path first (exact hash), then semantic path.
        """
        cache_key = self._embedder.build_cache_key(tool_name, arguments)
        key_hash = self._embedder.hash_key(cache_key)
        now = datetime.now(timezone.utc)

        # --- Fast path: exact hash match ---
        result = await session.execute(
            text("""
                SELECT response_payload, created_at, expires_at
                FROM semantic_cache
                WHERE tenant_id = :tenant_id
                  AND key_hash = :key_hash
                  AND expires_at > :now
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"tenant_id": tenant_id, "key_hash": key_hash, "now": now},
        )
        row = result.fetchone()
        if row is not None:
            logger.debug(
                "cache_hit_exact",
                tenant_id=tenant_id[:12],
                tool=tool_name,
            )
            return json.loads(row.response_payload)

        # --- Semantic path: cosine similarity ---
        embedding = self._embedder.embed(cache_key)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        result = await session.execute(
            text("""
                SELECT response_payload, created_at,
                       1 - (embedding <=> :embedding::vector) AS similarity
                FROM semantic_cache
                WHERE tenant_id = :tenant_id
                  AND tool_name = :tool_name
                  AND expires_at > :now
                  AND 1 - (embedding <=> :embedding::vector) >= :threshold
                ORDER BY similarity DESC
                LIMIT 1
            """),
            {
                "tenant_id": tenant_id,
                "tool_name": tool_name,
                "embedding": embedding_str,
                "now": now,
                "threshold": self._similarity,
            },
        )
        row = result.fetchone()
        if row is not None:
            logger.debug(
                "cache_hit_semantic",
                tenant_id=tenant_id[:12],
                tool=tool_name,
                similarity=round(row.similarity, 4),
            )
            return json.loads(row.response_payload)

        logger.debug("cache_miss", tenant_id=tenant_id[:12], tool=tool_name)
        return None

    async def store(
        self,
        session: AsyncSession,
        tenant_id: str,
        tool_name: str,
        arguments: dict,
        response: dict,
    ) -> None:
        """Store a response in the cache."""
        cache_key = self._embedder.build_cache_key(tool_name, arguments)
        key_hash = self._embedder.hash_key(cache_key)
        embedding = self._embedder.embed(cache_key)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        payload = json.dumps(response, separators=(",", ":"))

        await session.execute(
            text("""
                INSERT INTO semantic_cache
                    (tenant_id, tool_name, key_hash, embedding, response_payload, created_at, expires_at)
                VALUES
                    (:tenant_id, :tool_name, :key_hash, :embedding::vector, :payload, :now, :expires_at)
                ON CONFLICT (tenant_id, key_hash)
                DO UPDATE SET
                    response_payload = EXCLUDED.response_payload,
                    embedding = EXCLUDED.embedding,
                    created_at = EXCLUDED.created_at,
                    expires_at = EXCLUDED.expires_at
            """),
            {
                "tenant_id": tenant_id,
                "tool_name": tool_name,
                "key_hash": key_hash,
                "embedding": embedding_str,
                "payload": payload,
                "now": now,
                "expires_at": expires_at,
            },
        )
        await session.commit()

        logger.debug(
            "cache_store",
            tenant_id=tenant_id[:12],
            tool=tool_name,
            ttl=self._ttl_seconds,
        )

    async def invalidate(
        self,
        session: AsyncSession,
        tenant_id: str,
        tool_name: str | None = None,
    ) -> int:
        """Invalidate cache entries.

        If tool_name is provided, invalidate only that tool's entries.
        Otherwise invalidate all entries for the tenant.
        Returns the number of rows deleted.
        """
        if tool_name:
            result = await session.execute(
                text("""
                    DELETE FROM semantic_cache
                    WHERE tenant_id = :tenant_id AND tool_name = :tool_name
                """),
                {"tenant_id": tenant_id, "tool_name": tool_name},
            )
        else:
            result = await session.execute(
                text("""
                    DELETE FROM semantic_cache
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id},
            )
        await session.commit()
        count = result.rowcount
        logger.info(
            "cache_invalidate",
            tenant_id=tenant_id[:12],
            tool=tool_name,
            deleted=count,
        )
        return count

    async def cleanup_expired(self, session: AsyncSession) -> int:
        """Delete expired entries (TTL enforcement)."""
        now = datetime.now(timezone.utc)
        result = await session.execute(
            text("DELETE FROM semantic_cache WHERE expires_at <= :now"),
            {"now": now},
        )
        await session.commit()
        return result.rowcount

    async def cleanup_gdpr(self, session: AsyncSession, max_age_hours: int = 24) -> int:
        """Hard-delete entries older than max_age_hours (GDPR compliance)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        result = await session.execute(
            text("DELETE FROM semantic_cache WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()
        count = result.rowcount
        if count > 0:
            logger.info("cache_gdpr_cleanup", deleted=count, max_age_hours=max_age_hours)
        return count
