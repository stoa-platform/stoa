# REWRITE-BUGS — CAB-1889 CP-1

Bugs and smells surfaced while rewriting the GitProvider abstraction. Not fixed in CP-1 — tracked here for future tickets.

---

## BUG-01 — `_project` leak in `iam_sync_service.py`

**File** : `src/services/iam_sync_service.py:205-209`
**Nature** : same abstraction leak pattern as the router, but in a service layer:
```python
if not git_service._project:
    ...
tree = git_service._project.repository_tree(path="tenants", ref="main")
```
**Why it matters** : `iam_sync_service` goes through `git_service` (the singleton). If `GIT_PROVIDER=github` is active, `git_service` is a `GitHubService` with **no** `_project` attribute — this branch is silently dead. The sync never runs for GitHub-backed deployments.
**Fix** : swap to `await git_service.list_tree("tenants", ref="main")` (CP-1 added the method). No new capability needed.

---

## BUG-02 — `_project` leak in `deployment_orchestration_service.py`

**File** : `src/services/deployment_orchestration_service.py:102, 122`
**Nature** : same leak, reads `git_service._project.commits.list(ref_name="main", per_page=1)`.
**Why it matters** : same as BUG-01 — the head-commit lookup is GitLab-only. GitHub returns the `_project is None` branch.
**Fix** : swap to `await git_service.get_head_commit_sha(ref="main")` (already in the ABC).

---

## BUG-03 — Semaphore bypass on `GitLabService.create_file/update_file/delete_file`

**File** : `src/services/git_service.py:621-663`
**Nature** : `create_file`, `update_file`, `delete_file`, `batch_commit` call `self._gl.projects.get(project_id)` bypassing the `_fetch_with_protection` semaphore+retry wrapper (CAB-688 obligation #1).
**Why it matters** : under parallel load, write ops can blow past the 10-connection ceiling and trigger 429s with no retry.
**Fix** : wrap inside `_fetch_with_protection` or sleep the wrapper into the method body.

---

## BUG-04 — Provider-aware logic in base ABC  **[CLOSED — CAB-1889 CP-2 C.2#3]**

**File** : `src/services/git_provider.py:175-194` (`get_api_override` default impl).
**Nature** : the base class inspected `settings.GIT_PROVIDER` to pick a `project_id` format. That was leaky — the base class shouldn't know about concrete providers.
**Fix (shipped)** : the ABC now reads `settings.git.active_catalog_project_id` (provider-agnostic accessor introduced by CAB-1889 CP-2 C.1). Each concrete service (`GitHubService`, `GitLabService`) continues to own its internal `_catalog_project_id` helper; the ABC no longer branches on provider identity.

---

## BUG-05 — `write_file` consolidation flips POST semantics silently (CP-1 introduced)

**File** : `src/routers/git.py:166-184` (POST `/files/{path}`).
**Nature** : before CP-1, the router ran `get_file` + `files.get(...).save(...)` for updates — two round-trips. After CP-1, it calls `write_file` which does `get_file` + `files.get(...).save(...)` inside the provider — same semantics, but a caller inspecting GitLab logs sees the second `files.get()` attributed to `write_file` instead of the endpoint handler.
**Why it matters** : diagnostic only — no functional change, no user-visible change. Worth noting in the CP-1 commit message for log-grepping oncall folks.
**Fix** : none required.

---

## BUG-06 — `list_path_commits` in GitHub returns up to `limit` via Python slicing (CP-1 introduced)

**File** : `src/services/github_service.py` (new `list_path_commits` method).
**Nature** : PyGithub's `get_commits(path=...)` is paginated; `[:limit]` pulls pages until `limit` is satisfied. Unlike GitLab's `per_page=limit`, GitHub's implementation may fetch more than one page when `limit > 30`. No API-level cap enforcement.
**Why it matters** : minor efficiency, not correctness. Call sites in the router cap `limit <= 100` (Query constraint).
**Fix** : `itertools.islice(repo.get_commits(...), limit)` for iterator-friendly cap, or accept current behavior.
