"""``CatalogReconcilerWorker`` — Phase 3 scaffold (NotImplementedError on tick).

Spec §6.6 (CAB-2186 B-WORKER).

Lifecycle mirrors the existing in-tree workers in ``main.py``: ``start()`` is
the long-running coroutine; ``stop()`` flips a shutdown flag. Phase 4 fills
the inner loop per spec §6.6.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..catalog_git_client.protocol import CatalogGitClient

logger = logging.getLogger(__name__)


class CatalogReconcilerWorker:
    """Async loop reconciling ``api_catalog`` against ``stoa-catalog`` Git.

    Phase 3 stub: ``start()`` raises ``NotImplementedError`` on the first tick
    once the flag-gated startup hook in ``main.py`` reaches it. The flag is
    OFF by default, so production behaviour is unchanged.
    """

    def __init__(
        self,
        *,
        catalog_git_client: CatalogGitClient | None = None,
        db: Any | None = None,
        interval_seconds: int = 10,
    ) -> None:
        self._catalog_git_client = catalog_git_client
        self._db = db
        self._interval_seconds = interval_seconds
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        """Run the reconciler loop until ``stop()`` is called.

        Phase 3 stub. Phase 4 implements spec §6.6.
        """
        logger.info("catalog_reconciler.start: scaffold tick (raises NotImplementedError)")
        raise NotImplementedError(
            "CatalogReconcilerWorker.start: stub Phase 3. "
            "Implementation in Phase 4 — see CAB-2186 (B-WORKER) and spec §6.6."
        )

    async def stop(self) -> None:
        """Signal the loop to exit at the next iteration boundary."""
        self._shutdown.set()
