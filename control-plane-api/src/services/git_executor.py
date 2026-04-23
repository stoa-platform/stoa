"""Bounded sync-in-async executor for provider SDKs (CP-1 C.1/C.4/C.5).

PyGithub and python-gitlab are synchronous clients. Calling them directly
from ``async def`` handlers blocks the asyncio event loop for the full
HTTP round-trip plus any library-side throttle/retry. Every synchronous
SDK call MUST be routed through :func:`run_sync` so the loop stays
responsive under load.

Responsibilities:
  - Offload to the default thread executor via ``asyncio.to_thread``.
  - Cap applicative concurrency via per-purpose semaphores.
  - Enforce a per-call timeout.

Explicitly NOT responsible:
  - Retry policy. PyGithub (``seconds_between_requests`` / ``retry``) and
    python-gitlab (``obey_rate_limit`` / ``max_retries``) already ship
    retry semantics for 429 / transient failures. Stacking a second opaque
    layer here would fight those defaults.

Implementation rule for callers (do not violate):
  The entire SDK interaction — including iteration over ``PaginatedList``
  objects and ``.decoded_content`` access on lazy ``ContentFile`` — MUST
  happen inside the closure passed to :func:`run_sync`. Returning a lazy
  object and iterating it after ``await`` re-introduces C.1.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

# ── GitLab ──────────────────────────────────────────────────────────
# CAB-688 obligation #1: cap applicative concurrency at 10.
# Now applied uniformly across every GitLab SDK call via ``run_sync``.
GITLAB_SEMAPHORE = asyncio.Semaphore(10)

# ── GitHub ──────────────────────────────────────────────────────────
# Read-side cap. 10 matches the GitLab setting.
GITHUB_READ_SEMAPHORE = asyncio.Semaphore(10)

# GitHub REST "Repository contents" endpoints (create/update/delete file)
# MUST be serialised — parallel requests against the Contents API are
# documented as causing conflicts. Applies to create_file, update_file,
# delete_file, and any high-level path (write_file, create_api, ...)
# that reaches those endpoints. Also used for the Git-Data tree path in
# batch_commit to keep a single write lane.
GITHUB_CONTENTS_WRITE_SEMAPHORE = asyncio.Semaphore(1)

# Non-Contents writes (pull requests, branches, webhooks) tolerate
# moderate concurrency.
GITHUB_META_WRITE_SEMAPHORE = asyncio.Semaphore(5)

# ── Timeouts ────────────────────────────────────────────────────────
DEFAULT_TIMEOUT_S = 30.0
BATCH_TIMEOUT_S = 60.0

T = TypeVar("T")


async def run_sync(
    fn: Callable[..., T],
    /,
    *args: object,
    semaphore: asyncio.Semaphore,
    timeout: float = DEFAULT_TIMEOUT_S,
    op_name: str = "git_sync_call",
    **kwargs: object,
) -> T:
    """Offload a sync SDK call under semaphore + timeout.

    Args:
        fn: The synchronous function to run. Must fully materialise any
            lazy SDK objects before returning (see module docstring).
        *args, **kwargs: Forwarded to ``fn``.
        semaphore: The applicative concurrency cap appropriate for this
            call (one of the module-level semaphores).
        timeout: Per-call timeout in seconds.
        op_name: Short label for logs on timeout.

    Raises:
        TimeoutError: If the call exceeds ``timeout`` seconds. Note that
            the underlying thread keeps running to completion — this is
            an asyncio-level cancellation, not a thread-level kill.
        Exception: Any exception raised by ``fn``.
    """
    async with semaphore:
        try:
            async with asyncio.timeout(timeout):
                return await asyncio.to_thread(fn, *args, **kwargs)
        except TimeoutError:
            logger.warning(
                "git_sync_call timeout: op=%s timeout=%.1fs",
                op_name,
                timeout,
            )
            raise
