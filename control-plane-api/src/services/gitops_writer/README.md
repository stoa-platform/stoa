# gitops_writer

GitOps-first API creation flow. Writes to `stoa-catalog` Git remote first, then
projects to `api_catalog` from the re-read content.

## Status

- ✅ Phase 3 — scaffold mergé (PR #2605)
- ✅ Phase 4-1 — primitives unitaires (this PR)
  - `paths.py`: `canonical_catalog_path`, `parse_canonical_path`, `is_uuid_shaped`
  - `hashing.py`: `compute_catalog_content_hash` (from Phase 3)
  - `advisory_lock.py`: `advisory_lock_key` (from Phase 3)
- ⏳ Phase 4-2 — orchestration (`create_api()` flow + handler wiring)

## Spec

`specs/api-creation-gitops-rewrite.md` v1.0 (PR #2600 + §11 audit-informed PR
#2602).

## What this module owns (post-Phase 4-1)

- **`paths.canonical_catalog_path(tenant_id, api_name)`** — single source of
  truth for the layout `tenants/{tenant_id}/apis/{api_name}/api.yaml`. Refuses
  UUID-shaped segments (CAB-2187 B10).
- **`paths.parse_canonical_path(git_path)`** — inverse, used by the reconciler
  tick.
- **`hashing.compute_catalog_content_hash(api_yaml_bytes)`** — sha256 hex of
  the api.yaml bytes. Idempotency anchor (§6.2.1).
- **`advisory_lock.advisory_lock_key(tenant_id, api_id)`** — deterministic
  int64 for `pg_advisory_lock` (§6.8).

## What's NOT in this PR (Phase 4-2)

- `GitOpsWriter.create_api()` — still a stub raising `NotImplementedError`
- Handler `POST /v1/tenants/{tenant_id}/apis` modifications
- `main.py` runtime task spawn (kept flag-gated by Phase 3)

## Non-goals (this rewrite)

- Update / delete / promote API
- Migration of legacy UUID drift rows (cat B)
- Soft-delete of orphans (cat C / B11 — deferred)
- UAC V2 hash function (`compute_uac_spec_hash`)

## Phase 4-2 dev guide

The 18-step flow is fully documented in spec §6.5. Phase 4-2 will:

1. Implement `GitOpsWriter.create_api(tenant_id, contract_payload, actor)`
   per spec §6.5 (cases A/B/C, retry loop on SHA mismatch).
2. Add the route branch in `routers/apis.py` gated by
   `settings.GITOPS_CREATE_API_ENABLED`.
3. Wire the reconciler tick body (§6.6) using the primitives shipped here.

## Backlog tickets

- CAB-2184 (B-CLIENT) — `GitHubContentsCatalogClient` real impl ✅ Phase 4-1
- CAB-2185 (B-FLOW) — inverse create flow per spec §6.5 ⏳ Phase 4-2
- CAB-2187 (B10) — `git_path` UUID drift prevention ✅ Phase 4-1
- CAB-2182 (B-HASH) — content hash ✅ Phase 3
- CAB-2186 (B-WORKER) — reconciler tick body ⏳ Phase 4-2
