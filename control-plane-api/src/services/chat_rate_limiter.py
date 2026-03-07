"""Chat rate limiter — sliding window, in-memory (CAB-1655).

Provides per-user and per-tenant rate limiting for chat endpoints.
No Redis dependency — uses a simple dict of deques with timestamps.

Limits (configurable via env vars):
- Per-user: 20 messages/min, 5 tool calls/min
- Per-tenant: 100 messages/min
"""

from __future__ import annotations

import time
from collections import deque
from typing import Literal

from ..config import settings

# Window size in seconds
_WINDOW_SECONDS = 60

# Store: key → deque of timestamps (epoch floats)
_buckets: dict[str, deque[float]] = {}


def _bucket_key(scope: str, scope_id: str, action: Literal["message", "tool_call"]) -> str:
    return f"chat:{scope}:{scope_id}:{action}"


def _prune_and_count(key: str) -> int:
    """Prune expired entries and return count of entries in the current window."""
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    bucket = _buckets.get(key)
    if bucket is None:
        return 0
    # Remove expired entries from the left
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    return len(bucket)


def _record(key: str) -> None:
    """Record a new event in the bucket."""
    if key not in _buckets:
        _buckets[key] = deque()
    _buckets[key].append(time.monotonic())


def check_rate_limit(
    user_id: str,
    tenant_id: str,
    action: Literal["message", "tool_call"] = "message",
) -> tuple[bool, str | None, int | None]:
    """Check if the request is within rate limits.

    Returns:
        (allowed, reason, retry_after_seconds)
        - allowed=True, reason=None, retry_after=None if OK
        - allowed=False, reason=str, retry_after=int if rate limited
    """
    # Per-user check
    user_key = _bucket_key("user", user_id, action)
    user_count = _prune_and_count(user_key)

    if action == "message":
        user_limit = settings.CHAT_RATE_LIMIT_USER_MESSAGES
    else:
        user_limit = settings.CHAT_RATE_LIMIT_USER_TOOL_CALLS

    if user_count >= user_limit:
        return False, f"User rate limit exceeded: {user_count}/{user_limit} {action}s per minute", _WINDOW_SECONDS

    # Per-tenant check (messages only — tool calls are implicitly capped by message limit)
    if action == "message":
        tenant_key = _bucket_key("tenant", tenant_id, "message")
        tenant_count = _prune_and_count(tenant_key)
        tenant_limit = settings.CHAT_RATE_LIMIT_TENANT_MESSAGES

        if tenant_count >= tenant_limit:
            return (
                False,
                f"Tenant rate limit exceeded: {tenant_count}/{tenant_limit} messages per minute",
                _WINDOW_SECONDS,
            )

    return True, None, None


def record_event(
    user_id: str,
    tenant_id: str,
    action: Literal["message", "tool_call"] = "message",
) -> None:
    """Record a chat event for rate limiting purposes."""
    _record(_bucket_key("user", user_id, action))
    if action == "message":
        _record(_bucket_key("tenant", tenant_id, "message"))


def reset_all() -> None:
    """Clear all rate limit buckets. For testing only."""
    _buckets.clear()
