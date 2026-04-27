# catalog_git_client

`CatalogGitClient` Protocol + first PyGithub Contents API implementation for
`stoa-catalog`.

## Status

- ✅ Phase 3 — Protocol figé + scaffold (PR #2605)
- ✅ Phase 4-1 — `GitHubContentsCatalogClient` real implementation (this PR)
- ⏳ Phase 4-2 — consumed by `GitOpsWriter.create_api()` and the reconciler
  tick

## Spec

`specs/api-creation-gitops-rewrite.md` §6.7 (CAB-2184 B-CLIENT).

## Contract (5 methods, spec §6.7)

- `get(path)` → `RemoteFile | None` — read at HEAD on default branch; `None`
  on 404
- `create_or_update(path, content, expected_sha, actor, message)` →
  `RemoteCommit` — optimistic CAS via `expected_sha`; raises
  `CatalogShaConflictError` on mismatch
- `read_at_commit(path, commit_sha)` → `bytes | None` — read at a specific
  commit; `None` on 404
- `latest_file_commit(path)` → `str` — first commit SHA in history of `path`
- `list(glob_pattern)` → `list[str]` — recursive tree walk filtered by
  `fnmatch`

## Implementation notes

- No `git` CLI / worktree dependency (garde-fou §9.10).
- Reuses the existing `services.github_service.GitHubService` PyGithub
  connection. Caller is responsible for `connect()` / `disconnect()`.
- All PyGithub calls are routed through `git_executor.run_sync` under the
  `GITHUB_READ_SEMAPHORE` (cap 10) or `GITHUB_CONTENTS_WRITE_SEMAPHORE`
  (cap 1, serial). Lazy `ContentFile` attributes are materialised inside the
  closure to preserve the CP-1 C.1 invariant (no sync-in-async leak).
- `CatalogShaConflictError` is raised on HTTP 409 / 422 from the Contents
  API so the writer's spec §6.5 step 10 retry loop can re-evaluate Case
  A/B/C.
