# gitops_writer

GitOps-first API creation flow. Writes to `stoa-catalog` Git remote first, then
projects to `api_catalog` from the re-read content.

**Status**: Phase 3 scaffold (stubs only). Implementation lands in Phase 4.

## Spec

`specs/api-creation-gitops-rewrite.md` v1.0 (PR #2600 + §11 audit-informed PR
#2602).

## Backlog (Phase 4)

- CAB-2184 (B-CLIENT) — `CatalogGitClient` abstraction + PyGithub impl
- CAB-2185 (B-FLOW) — inverse create flow per spec §6.5
- CAB-2187 (B10) — `git_path` UUID drift prevention test
- CAB-2182 (B-HASH) — already implemented in `hashing.py`
- CAB-2186 (B-WORKER) — reconciler tick implementation

## Non-goals (this rewrite)

- Update / delete / promote API
- Migration of legacy UUID drift rows (cat B)
- Soft-delete of orphans (cat C / B11 — deferred)
- UAC V2 hash function (`compute_uac_spec_hash`)

## Phase 4 dev guide

The 18-step flow is fully documented in spec §6.5. Start with:

1. Wire `CatalogGitClient` (CAB-2184) — implement
   `GitHubContentsCatalogClient` against existing `services.github_service`.
2. Wire `GitOpsWriter.create_api` (CAB-2185) — three idempotent cases A/B/C
   per spec §6.2.
3. Add the route branch in `routers/apis.py` gated by
   `settings.GITOPS_CREATE_API_ENABLED`.

## Files implemented in Phase 3 (deterministic, real code)

- `hashing.py` — `compute_catalog_content_hash` (sha256 hex of api.yaml bytes)
- `advisory_lock.py` — `advisory_lock_key` (deterministic int64 from sha256)
