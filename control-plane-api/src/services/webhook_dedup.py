"""In-memory webhook dedup cache (CP-1 H.1).

Both GitHub and GitLab re-deliver the same webhook on timeout, on manual
redelivery, or on some transient failures. Without dedup the pipeline
runs twice: Kafka publish x2, trace x2, and the "already exists" path is
either counted as an error (H.8 pre-fix) or masked as success (H.8
post-fix). Either way the downstream state drifts.

This module implements a three-state claim/process/done state machine
keyed on ``(source, delivery_id)``:

- ``claim`` — inserted before any side effect (after auth). Signals
  that this delivery is being processed RIGHT NOW by this replica. A
  concurrent retry hitting the same key while still ``claim`` returns
  ``in-flight``.
- ``done`` — set after the pipeline completes successfully. A later
  redelivery hitting the same key returns ``duplicate`` with zero
  side effects.
- on exception → the claim is explicitly **released**, leaving no entry
  so the next retry enters the normal flow. This is the bit that
  matters: a first attempt that passes auth but fails midway must not
  turn the next retry into a spurious "duplicate forever".

Important scope notes:

- **Single-replica only.** The store is per-process. If CP-API scales
  horizontally, two replicas may each process the same delivery. The
  Helm chart currently pins ``replicas: 1`` ; a Redis / Postgres-backed
  successor is tracked for P2/P3.
- **Header priority — GitLab.** ``Idempotency-Key`` (stable across
  retries, documented as the dedup primitive) first, with fallback to
  ``X-Gitlab-Webhook-UUID`` (per-webhook unique id). ``X-Gitlab-Event-
  UUID`` is **never** used as primary key: it is shared across
  recursive webhooks so deduping on it drops legitimate events.
- **Header priority — GitHub.** ``X-GitHub-Delivery`` is the canonical
  id per GitHub docs.

The cache is bounded: 10 000 entries, 24 h TTL. Under typical webhook
volumes this covers GitHub's standard redelivery window. Entries past
the TTL are lazily evicted on read ; on capacity overflow the oldest
entry is dropped (FIFO) before the new one is added.
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections import OrderedDict
from dataclasses import dataclass


class DedupVerdict(enum.Enum):
    """Outcome of a claim attempt."""

    NEW = "new"
    """First time we see this delivery — caller must process it."""

    DUPLICATE = "duplicate"
    """Already processed successfully — caller must return cached result."""

    IN_FLIGHT = "in-flight"
    """Another request is currently processing this delivery."""


@dataclass
class DedupEntry:
    state: str  # "claim" | "done"
    inserted_at: float
    result: dict | None = None  # populated on mark_done


class WebhookDedupCache:
    """TTL + capacity-bounded in-memory dedup keyed by (source, id)."""

    def __init__(self, *, capacity: int = 10_000, ttl_seconds: float = 86_400.0) -> None:
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._entries: OrderedDict[tuple[str, str], DedupEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    def _expired(self, entry: DedupEntry, now: float) -> bool:
        return now - entry.inserted_at > self._ttl

    async def claim(self, source: str, delivery_id: str) -> tuple[DedupVerdict, dict | None]:
        """Attempt to claim a delivery slot for this process.

        Returns:
            (NEW, None) — no prior record, caller must process then call
                mark_done or release.
            (DUPLICATE, cached_result) — already processed successfully.
            (IN_FLIGHT, None) — another caller is still processing.
        """
        key = (source, delivery_id)
        now = time.monotonic()
        async with self._lock:
            entry = self._entries.get(key)
            if entry is not None and not self._expired(entry, now):
                if entry.state == "done":
                    return DedupVerdict.DUPLICATE, entry.result
                return DedupVerdict.IN_FLIGHT, None

            # Evict lazily if expired or missing.
            if entry is not None:
                self._entries.pop(key, None)

            # Enforce capacity BEFORE insert.
            while len(self._entries) >= self._capacity:
                self._entries.popitem(last=False)

            self._entries[key] = DedupEntry(state="claim", inserted_at=now)
            return DedupVerdict.NEW, None

    async def mark_done(self, source: str, delivery_id: str, result: dict) -> None:
        """Promote a claim to 'done' and cache the pipeline result."""
        key = (source, delivery_id)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                # Someone released before us — insert a fresh 'done' entry
                # so a later retry still gets DUPLICATE instead of NEW.
                self._entries[key] = DedupEntry(
                    state="done", inserted_at=time.monotonic(), result=result
                )
                return
            entry.state = "done"
            entry.inserted_at = time.monotonic()
            entry.result = result
            self._entries.move_to_end(key)

    async def release(self, source: str, delivery_id: str) -> None:
        """Remove a claim on failure so the next retry is not 'duplicate'.

        This is the critical piece of H.1: a first attempt that
        authenticates successfully but fails mid-pipeline must NOT turn
        the next redelivery into a spurious DUPLICATE (which would lose
        the event).
        """
        key = (source, delivery_id)
        async with self._lock:
            self._entries.pop(key, None)

    async def size(self) -> int:
        async with self._lock:
            return len(self._entries)

    async def reset(self) -> None:
        """Test-only helper."""
        async with self._lock:
            self._entries.clear()


# Module-level singleton. Two replicas get two independent caches —
# documented limitation, P2/P3 moves to Redis.
webhook_dedup_cache = WebhookDedupCache()


def gitlab_delivery_id(
    idempotency_key: str | None, webhook_uuid: str | None
) -> str | None:
    """Compute the dedup key for a GitLab webhook.

    Priority:
      1. ``Idempotency-Key`` — documented as stable across retries.
      2. ``X-Gitlab-Webhook-UUID`` — per-webhook unique id (fallback).

    Never use ``X-Gitlab-Event-UUID`` here: it is shared across
    recursive webhooks, so deduping on it swallows legitimate events.
    """
    key = (idempotency_key or "").strip()
    if key:
        return f"gitlab:idem:{key}"
    key = (webhook_uuid or "").strip()
    if key:
        return f"gitlab:webhook:{key}"
    return None


def github_delivery_id(delivery_header: str | None) -> str | None:
    """Compute the dedup key for a GitHub webhook.

    Uses ``X-GitHub-Delivery`` which GitHub documents as the canonical
    delivery identifier (stable across manual redelivery, new on
    automatic redelivery post-timeout).
    """
    key = (delivery_header or "").strip()
    if key:
        return f"github:{key}"
    return None
