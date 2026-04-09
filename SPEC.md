# Spec: CAB-2012 — Console Commit-on-Write: Async Git Sync on API CRUD

> Council: 8.25/10 Go (spec). Phase 1b of MEGA CAB-2010. Depends on CAB-2011.

## Problem

The Console writes API definitions to the database only. The Git catalog (`stoa-catalog`) diverges silently — there is no mechanism to propagate CRUD operations to Git after a DB write.

## Goal

Every API create/update/delete in the Console produces a corresponding Git commit in `stoa-catalog` within 30 seconds, without ever blocking the HTTP response.

## Architecture

```
Console -> POST /apis -> DB write (sync) -> Kafka emit (fire-and-forget)
                                                 |
                                        Topic: stoa.api.lifecycle
                                        Events: api-created, api-updated, api-deleted
                                                 |
                                        GitSyncWorker (consumer)
                                                 |
                                        GitHubService.create_api / update_api / delete_api
                                                 |
                                        stoa-catalog repo (Git commit)
```

## Acceptance Criteria

- [x] AC1: api-created -> Git commit in stoa-catalog
- [x] AC2: api-updated -> Git commit updates api.yaml
- [x] AC3: api-deleted -> API directory removed from stoa-catalog
- [x] AC4: GIT_SYNC_ON_WRITE=false disables Git operations
- [x] AC5: Retry 3x with exponential backoff (2s, 4s, 8s)
- [x] AC6: Idempotent (no commit if content identical)
- [x] AC7: Kafka failure doesn't block HTTP response

## Edge Cases

| # | Case | Expected | Priority |
|---|------|----------|----------|
| E1 | GitHub rate limit (403) | Retry with backoff | Must |
| E2 | Duplicate event | No-op (idempotent) | Must |
| E3 | Tenant missing in Git | Auto-create via _ensure_tenant_exists() | Must |
| E5 | Worker crash mid-retry | Kafka re-delivers (uncommitted offset) | Must |
| E7 | GitHubService not initialized | Skip gracefully | Must |

## Out of Scope

- Reverse sync (Git -> DB) — CAB-2016
- UI feedback showing Git sync status
- Tenant CRUD sync, Policy sync to Git
