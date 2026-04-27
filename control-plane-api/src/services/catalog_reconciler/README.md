# catalog_reconciler

Async in-tree worker that reconciles `api_catalog` against `stoa-catalog` Git.

## Status

- ✅ Phase 3 — scaffold mergé (PR #2605); `start()` still raises
  `NotImplementedError`
- ✅ Phase 4-1 — projection + classifier primitives (this PR)
- ⏳ Phase 4-2 — `start()` loop body + DB upsert wiring

The worker is flag-gated by `GITOPS_CREATE_API_ENABLED` (default OFF), so it
is never started in production until Phase 4-2 ships.

## Spec

`specs/api-creation-gitops-rewrite.md` §6.5 step 14, §6.6, §6.9, §6.14, §11
(CAB-2186 B-WORKER + CAB-2188 B12 + CAB-2180 B-CATALOG).

## Modules

- `worker.py` — `CatalogReconcilerWorker.start()` loop (stub)
- `classifier.py` — `classify_legacy()` returning `LegacyCategory` (6
  categories: `HEALTHY_ADOPTABLE`, `UUID_HARD_DRIFT`, `ORPHAN_DB`,
  `PRE_GITOPS`, `GITOPS_CREATED`, `ABSENT`)
- `projection.py`:
  - `ApiCatalogProjection` — frozen dataclass for §6.9 mapping
  - `render_api_catalog_projection()` — parsed YAML → projection
  - `row_matches_projection()` — drift detection (ignores `target_gateways`,
    `openapi_spec`, `metadata`, `id`)
  - `project_to_api_catalog()` — transactional upsert (preserves
    `target_gateways`, `openapi_spec`, `metadata`, `id` PK on UPDATE)

## What's NOT in this PR (Phase 4-2)

- `CatalogReconcilerWorker.start()` body — still raises
  `NotImplementedError`
- `main.py` flag-gating change (kept identical to Phase 3)
- Any reads of `api_sync_status` (the new table is created lazily by
  Phase 4-2 alongside the loop body)
