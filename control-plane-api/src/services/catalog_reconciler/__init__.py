"""Catalog reconciler — Phase 3 scaffold.

Spec §6.6 (CAB-2186 B-WORKER + CAB-2188 B12 classifier).

Async in-tree worker that loops every ``CATALOG_RECONCILE_INTERVAL_SECONDS``
to reconcile ``api_catalog`` against ``stoa-catalog`` Git remote. Status:
scaffold; first tick raises ``NotImplementedError`` — Phase 4 will wire the
full loop per spec §6.6.
"""

from .classifier import LegacyCategory, classify_legacy
from .projection import render_api_catalog_projection, row_matches_projection
from .worker import CatalogReconcilerWorker

__all__ = [
    "CatalogReconcilerWorker",
    "LegacyCategory",
    "classify_legacy",
    "render_api_catalog_projection",
    "row_matches_projection",
]
