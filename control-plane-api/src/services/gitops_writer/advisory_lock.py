"""Postgres advisory lock key derivation.

Spec §6.8 (CAB-2185 B-FLOW).

The key is derived from ``sha256("stoa:gitops:{tenant_id}:{api_id}")[:8]`` and
returned as a signed 64-bit integer. ``hash()`` Python natif is forbidden — it
is process-randomised on most builds and would make the lock non-deterministic
between processes (writer vs reconciler vs CLI).
"""

from __future__ import annotations

import hashlib


def advisory_lock_key(tenant_id: str, api_id: str) -> int:
    """Return a deterministic 64-bit signed int for ``pg_advisory_lock``.

    Scope is ``(tenant_id, api_id)``; both are slugs (never UUID).
    """
    raw = f"stoa:gitops:{tenant_id}:{api_id}".encode()
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big", signed=True)
