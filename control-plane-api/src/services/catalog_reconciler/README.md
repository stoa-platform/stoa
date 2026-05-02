# catalog_reconciler

Async in-tree worker that reconciles `api_catalog` against `stoa-catalog` Git.

## Status

- ✅ Phase 3 — scaffold mergé (PR #2605); `start()` raised
  `NotImplementedError`
- ✅ Phase 4-1 — projection + classifier primitives (PR #2607)
- ✅ Phase 4-2 — `start()` / `_reconcile_iteration()` loop bodies (this PR)

The worker is flag-gated by `GITOPS_CREATE_API_ENABLED` (default OFF), so it
is never started in production until a tenant is added to
`GITOPS_ELIGIBLE_TENANTS` (Phase 6 strangler).

## Spec

`specs/api-creation-gitops-rewrite.md` §6.5 step 14, §6.6, §6.9, §6.14, §11
(CAB-2186 B-WORKER + CAB-2188 B12 + CAB-2180 B-CATALOG).

Gateway runtime DR coverage is specified separately in
`specs/catalog-gateway-dr-reconciliation.md`.

## Modules

- `worker.py` — `CatalogReconcilerWorker.start()` loop. Each tick:
  - lists `tenants/*/apis/*/api.yaml` from the Git remote
  - reads the preferred sibling `openapi.*` / `swagger.*` file and
    materializes it into `api_catalog.openapi_spec`
  - classifies each row via `classify_legacy()`
  - cat ABSENT / A / GITOPS_CREATED → projection (with
    `pg_try_advisory_xact_lock`)
  - cat B / C / D → log `drift_*` status, no auto-repair
  - DB orphan sweep at end of tick (cat C / D rows not seen this tick)
- `classifier.py` — `classify_legacy()` returning `LegacyCategory` (6
  categories: `HEALTHY_ADOPTABLE`, `UUID_HARD_DRIFT`, `ORPHAN_DB`,
  `PRE_GITOPS`, `GITOPS_CREATED`, `ABSENT`)
- `projection.py`:
  - `ApiCatalogProjection` — frozen dataclass for §6.9 mapping
  - `render_api_catalog_projection()` — parsed YAML → projection
  - `row_matches_projection()` — drift detection (ignores `target_gateways`,
    `id`, timestamps and soft-delete state)
  - `project_to_api_catalog()` — transactional upsert (preserves
    `target_gateways` and `id` PK on UPDATE; projects `metadata` and
    `openapi_spec` from Git)
- `../catalog_api_definition.py` — shared catalog API normalization and
  gateway target extraction for flat and Kubernetes-style `api.yaml`
- `../catalog_deployment_reconciler.py` — materializes explicit Git catalog
  gateway targets into `GatewayDeployment(sync_status=PENDING)` rows

## What's NOT in this PR (out-of-scope, Phase 5+)

- Persistent `api_sync_status` table — Phase 4-2 logs sync transitions via
  structured logs. The schema lands alongside Phase 5 observability work.
- Auto-repair of legacy UUID drift (cat B) — separate cycle owns FK
  migration of `subscriptions.api_id`, gateway routes, etc.
- Soft-delete of orphans (cat C) — owned by the delete/prune cycle (B11).
- Migration of pre-GitOps DB-only rows (cat D) — same constraint as cat B.
- Kafka emission on the reconciler path — short-circuited (spec §6.13).
