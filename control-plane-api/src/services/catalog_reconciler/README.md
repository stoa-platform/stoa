# catalog_reconciler

Async in-tree worker that reconciles `api_catalog` against `stoa-catalog` Git.

**Status**: Phase 3 scaffold. `start()` raises `NotImplementedError` on the
first tick. Flag-gated by `GITOPS_CREATE_API_ENABLED` (default OFF), so the
worker is never started in production until Phase 4 ships.

## Spec

`specs/api-creation-gitops-rewrite.md` §6.6 (CAB-2186 B-WORKER) + §6.14 +
§11 (cat A/B/C/D classifier — CAB-2188).

## Modules

- `worker.py` — `CatalogReconcilerWorker.start()` loop (stub)
- `classifier.py` — `classify_legacy()` returning `LegacyCategory` (A/B/C/D)
- `projection.py` — `render_api_catalog_projection()` and
  `row_matches_projection()` (stubs)
