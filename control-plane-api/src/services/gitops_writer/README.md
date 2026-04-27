# gitops_writer

GitOps-first API creation flow. Writes to `stoa-catalog` Git remote first, then
projects to `api_catalog` from the re-read content.

## Status

- ✅ Phase 3 — scaffold mergé (PR #2605)
- ✅ Phase 4-1 — primitives unitaires (PR #2607)
  - `paths.py`: `canonical_catalog_path`, `parse_canonical_path`, `is_uuid_shaped`
  - `hashing.py`: `compute_catalog_content_hash`
  - `advisory_lock.py`: `advisory_lock_key`
- ✅ Phase 4-2 — orchestration (this PR)
  - `writer.py`: `GitOpsWriter.create_api()` 18-step flow per §6.5
  - `exceptions.py`: `InvalidApiNameError`, `LegacyCollisionError`,
    `InfrastructureBugError`, `GitOpsRaceExhaustedError`
  - Handler branch in `src/routers/apis.py`
  - Reconciler wiring in `src/main.py`

The flag `GITOPS_CREATE_API_ENABLED` defaults to `False`, and
`GITOPS_ELIGIBLE_TENANTS` defaults to `[]` — production behaviour is unchanged
until Phase 6 strangler explicitly populates the eligible-tenants list.

## Spec

`specs/api-creation-gitops-rewrite.md` v1.0 (PR #2600 + §11 audit-informed PR
#2602).

## What this module owns

- **`writer.GitOpsWriter`** — orchestrates the 18-step flow §6.5. Cases A
  (created), B (idempotent), C (`GitOpsConflictError`). Retries §6.5 step 10
  up to 3× on optimistic-CAS races, then raises `GitOpsRaceExhaustedError`
  (mapped to HTTP 503).
- **`paths.canonical_catalog_path(tenant_id, api_name)`** — layout
  `tenants/{tenant_id}/apis/{api_name}/api.yaml`. Refuses UUID-shaped
  segments (CAB-2187 B10).
- **`paths.parse_canonical_path(git_path)`** — inverse, used by the writer
  + reconciler tick.
- **`hashing.compute_catalog_content_hash(api_yaml_bytes)`** — sha256 hex of
  the api.yaml bytes. Idempotency anchor (§6.2.1).
- **`advisory_lock.advisory_lock_key(tenant_id, api_id)`** — deterministic
  int64 for `pg_advisory_lock` (§6.8).
- **`exceptions`** — typed exceptions mapped to HTTP status codes by the
  POST handler (`InvalidApiNameError` → 422, `LegacyCollisionError` /
  `GitOpsConflictError` → 409, `GitOpsRaceExhaustedError` → 503,
  `InfrastructureBugError` → 500).

## Out-of-scope (this rewrite)

- Update / delete / promote API
- Migration of legacy UUID drift rows (cat B)
- Soft-delete of orphans (cat C / B11 — deferred)
- UAC V2 hash function (`compute_uac_spec_hash`)
- Persistent `api_sync_status` table — sync state surfaces via structured
  logs in Phase 4-2; the dedicated table lands alongside Phase 5 / 6
  observability work.

## Backlog tickets

- CAB-2184 (B-CLIENT) — `GitHubContentsCatalogClient` real impl ✅ Phase 4-1
- CAB-2185 (B-FLOW) — inverse create flow per spec §6.5 ✅ Phase 4-2
- CAB-2187 (B10) — `git_path` UUID drift prevention ✅ Phase 4-1
- CAB-2188 (B12) — legacy 3-category collision policy ✅ Phase 4-2
- CAB-2182 (B-HASH) — content hash ✅ Phase 3
- CAB-2186 (B-WORKER) — reconciler tick body ✅ Phase 4-2
