# FIX-PLAN-CP1-P2

> Phase 1 plan for the CP-1 P2 batch (5 findings: M.2, M.4, M.5, M.6, L.1).
> Based on `control-plane-api/BUG-REPORT-CP-1.md` Rev 2.
> Branch: `fix/cp-1-p2-batch` (cut from `fix/cp-1-p1-batch` — rebase on `main` once P0+P1 land).
>
> **Status: APPROVED WITH CORRECTIONS (2026-04-23 pm)** — user arbitration applied
> directly in the fiches below. The material changes vs the initial draft are:
>
> 1. **M.2** — short-circuit is narrow: only when the PR/MR is *already merged*
>    (`pr.merged is True` / `mr.state == "merged"`). "Closed but unmerged" still
>    raises.
> 2. **M.4** — resolve the default branch **at the provider-method boundary**, not
>    only inside closures. Method signatures switch to `ref: str | None = None`
>    (and `branch: str | None = None`) with `settings.git.default_branch`
>    resolution inside each method. Otherwise callers that omit `ref` keep
>    silently targeting `"main"`.
> 3. **M.5** — retry only transient failures (network errors, `TimeoutError`,
>    429, 5xx). Fail fast on 401/403 and bad-repo-config. Backoff math fixed:
>    **3 attempts = 2 sleeps = 1s → 2s** (per-attempt timeout 15s, worst-case
>    ~48s).
> 4. **L.1** — option **A** for `list_commits`: `iterator=True` + `per_page=min(limit,100)`
>    + `itertools.islice(..., limit)`. Preserves the `limit` contract.
> 5. Commit-message/test-count doc inconsistency fixed: **10 regression tests**,
>    not 8.
>
> Everything else from the initial draft stands as-is (M.6 gather, ancillary
> sweep, no `per_page` tuning, no theatrical pre-fix tests).

---

## Anti-redundance sweep vs P0/P1

Confirmed **none of the 5 P2 findings were incidentally closed** by the P0 (`fix/cp-1-p0-batch`) or P1 (`fix/cp-1-p1-batch`) commits:

| Bug | Checked at | Still open? | Proof |
|---|---|---|---|
| M.2 | `github_service.py:1215-1225`, `git_service.py:1196-1204` | Yes | Both `merge_merge_request` closures go straight to `pr.merge()` / `mr.merge()` with no pre-check; GitHub still double-fetches via two `get_pull(iid)` around the merge call. |
| M.4 | 50 call-sites in `git_service.py` + `github_service.py`, plus 3 in `iam_sync_service.py`, `deployment_orchestration_service.py`, `routers/traces.py` | Yes | `grep -n 'ref="main"\|branch="main"'` returns 50 matches in provider services post-P1. No `settings.git.default_branch` exists. |
| M.5 | `git_service.py:138-158` (GitLab), `github_service.py:169-183` (GitHub) | Yes | Both `connect()` wrap their closure in `_gl_run` / `_gh_read` (15s timeout) but there is no retry loop. A single transient 500 at boot still yields "not connected" + 503 from every route. |
| M.6 | `github_service.py:565-570`, `git_service.py:910-929` | Yes | Sequential `for tenant_id in ...: servers.extend(await self.list_mcp_servers(tenant_id))` in both providers. No `asyncio.gather`. |
| L.1 | `git_service.py:792, 1124, 1169` | Yes | `project.branches.list()`, `project.mergerequests.list(state=state)`, `project.commits.list(path=path, per_page=limit)` all missing `get_all=True` / `iterator=True`. python-gitlab silently truncates to 20 for the first two; `list_commits` caps at `limit` but never paginates beyond. |

No bug is obsolete / already-fixed.

`L.2` was closed in `52ba19012` (P1) as explicitly documented in the bug report header. Not re-opening.

---

## Bug fiches

### M.2 — `merge_merge_request` not idempotent + double fetch

- **Résumé** : GitHub `merge_merge_request(iid)` calls `repo.get_pull(iid)` twice (once before `pr.merge()`, once after) and raises `GithubException` when the PR is already merged. GitLab mirrors the pattern: `mergerequests.get(iid)` → `mr.merge()` with no guard. Replaying a merge webhook after a manual merge surfaces as a 500 via `H.3` mapping.
- **Fichier:ligne** : `control-plane-api/src/services/github_service.py:1215-1225`, `control-plane-api/src/services/git_service.py:1196-1204`
- **Approche de fix (corrected)** :
  - GitHub : fetch `pr = repo.get_pull(iid)` once. Short-circuit **only** when `pr.merged is True` → return `_pr_to_ref(pr)` without calling `pr.merge()`. "Closed but unmerged" (`state=="closed"` and `merged is False`) does **not** short-circuit — it falls through to `pr.merge()` which will raise the correct provider error. After `pr.merge()` returns, re-fetch via `repo.get_pull(iid)` once to get the fresh state for the returned ref (PyGithub's `PullRequest.merge()` returns a `PullRequestMergeStatus`, it does not mutate `pr` in place — verified empirically against stubs; documenting the constraint in an inline comment).
  - GitLab : fetch `mr = project.mergerequests.get(iid)` once. Short-circuit **only** when `mr.state == "merged"` → return `_mr_to_ref(mr)`. Otherwise call `mr.merge()` — python-gitlab's `ProjectMergeRequest.merge()` does update the instance's attributes (documented), so the same `mr` is used for the returned ref without a second fetch.
- **Régression guard proposé** (2 tests) :
  - `test_regression_cp1_p2_merge_idempotent.py::test_github_merge_request_short_circuits_when_already_merged`
    - Stub PR with `merged=True` → assert `pr.merge()` **not called**, ref reflects merged state.
    - Secondary assertion in the **same** test: stub PR with `state="closed"` + `merged=False` → assert `pr.merge()` **is** called (raising the provider error). Proves the short-circuit is narrow.
  - `test_regression_cp1_p2_merge_idempotent.py::test_gitlab_merge_request_short_circuits_when_already_merged`
    - Mirror on GitLab: `state="merged"` → no `mr.merge()` call; `state="closed"` → `mr.merge()` is called.

---

### M.4 — Hardcoded `ref="main"` / `branch="main"` in provider closures

- **Résumé** : 50 closures in `git_service.py` + `github_service.py` pin `ref="main"` / `branch="main"` inline. Any tenant whose catalog uses `master` or a custom default branch silent-fails. The active `GitProviderConfig` has no `default_branch` field.
- **Fichier:ligne** :
  - `git_service.py` — 17 internal `ref="main"` literals (lines 183, 369, 383, 404, 487, 507, 530, 554, 596, 624, 651, 875, 897, 920, 1001, 1045) plus `branch="main"` defaults on `create_file/update_file/delete_file/batch_commit/remove_file/create_branch`.
  - `github_service.py` — 8 internal `ref="main"` literals (lines 372, 409, 435, 552, 893, 904, 1015, 1026) plus identical `branch="main"` defaults on write methods.
  - Ancillary callers (out of P2 scope but trivial): `iam_sync_service.py:210`, `deployment_orchestration_service.py:132`, `routers/traces.py:512` — will be swept too since the cost is zero.
- **Approche de fix (corrected — resolve at the provider-method boundary)** :
  1. Add `default_branch: str = "main"` to `GitProviderConfig` (single field — catalog repo is shared across providers). Hydrate from new env var `GIT_DEFAULT_BRANCH` (backed by `Settings.GIT_DEFAULT_BRANCH: str = "main"`); `"main"` stays as the default so omitted config = no behaviour change.
  2. **ABC update** (`git_provider.py`) : every method that currently has `ref: str = "main"` or `branch: str = "main"` (or `target_branch: str = "main"`) switches to `ref: str | None = None` / `branch: str | None = None`. 15 signatures affected: `get_file_content`, `list_files`, `create_file`, `update_file`, `delete_file`, `batch_commit`, `get_head_commit_sha`, `list_tree`, `read_file`, `write_file`, `remove_file`, `create_branch`, `create_merge_request`, and (indirectly) any override on the two impls. Docstrings updated: `ref` default now says "catalog default branch (from `settings.git.default_branch`)".
  3. **Impl resolution** : inside each provider method, the first statement resolves the local `effective_ref = ref if ref is not None else settings.git.default_branch` (mirror for `branch`). Closures read from the local — settings never touched from inside `run_sync` / `_gl_run` / `_gh_read`, preserving the C.1 invariant.
  4. **Internal hardcoded `"main"`** (list_tenants tree walks, tenant-scope helpers — 17 in GitLab, 8 in GitHub) : replace with the same `effective_ref` local. For methods that are not on the ABC and don't take a `ref` param today (e.g. `list_tenants`, `list_mcp_servers`, `create_mcp_server`), resolve `effective_ref = settings.git.default_branch` locally rather than extending the signature. Keeps the diff narrow and matches how the public API carries the override for callers that want one.
  5. **Ancillary call-sites** : `iam_sync_service.py:210`, `deployment_orchestration_service.py:132`, `routers/traces.py:512` — drop the explicit `ref="main"` / `git_branch="main"` argument so the new default kicks in. (For `routers/traces.py:512` this is a response-payload field; replace the literal with `settings.git.default_branch`.)
  6. **Callers with explicit `ref=...`** (iam_sync `list_tree`, deployment_orchestration `get_head_commit_sha`, tests) : unchanged — they already pass their own value.
- **Régression guard proposé** :
  - `test_regression_cp1_p2_default_branch.py::test_gitlab_list_tenants_uses_configured_default_branch`
  - `test_regression_cp1_p2_default_branch.py::test_github_list_apis_uses_configured_default_branch`
  - Scenario: monkeypatch `settings.git.default_branch = "develop"` → stub `repository_tree` / `get_contents` → invoke the service → assert the stub was called with `ref="develop"`, never `"main"`.

---

### M.5 — `connect()` has no retry at startup (both providers)

- **Résumé** : `GitLabService.connect()` and `GitHubService.connect()` each run their network round-trip inside `_gl_run` / `_gh_read` with a 15s timeout — but **no retry**. A single transient blip during CP-API boot (GitLab 502, GitHub rate-limit on `get_user`) leaves the service `not connected` and every route returns 503 until the pod is restarted.
- **Fichier:ligne** : `control-plane-api/src/services/git_service.py:138-158`, `control-plane-api/src/services/github_service.py:169-183`
- **Approche de fix (corrected — transient-only, 1s→2s)** :
  - 3 attempts total → **2 sleeps** → `1s → 2s` backoff. Per-attempt timeout stays at 15s (the value already in `_gl_run` / `_gh_read`). Worst-case startup delay: `3 × 15s + 1s + 2s = 48s` — intentional, documented in the log line.
  - Transient classification:
    - **Retry**: `asyncio.TimeoutError` / `TimeoutError`, `requests.exceptions.ConnectionError`, `requests.exceptions.Timeout`, GitLab `GitlabHttpError` with `response_code` in {429} ∪ 5xx, GitHub `GithubException` with `status` in {429} ∪ 5xx.
    - **Fail fast** (re-raise immediately, no sleep): GitLab `GitlabAuthenticationError` (401/403); GitHub `BadCredentialsException`, or `GithubException` with `status` in {401, 403, 404}; any other exception class (unknown errors shouldn't be retried blindly).
  - Implementation detail: the classification lives in a small module-level helper (`_is_transient_gitlab_error` / `_is_transient_github_error`) so tests can monkey-patch it easily and so the discrimination is auditable without scanning the retry loop. The loop re-raises the last transient error after 3 attempts.
- **Régression guard proposé** :
  - `test_regression_cp1_p2_connect_retry.py::test_gitlab_connect_retries_on_transient_and_succeeds`
    - Scenario: stub closure to raise `requests.exceptions.ConnectionError` twice then succeed on the third call → assert `connect()` returns ok + exactly 3 attempts observed + `asyncio.sleep` called with `1` then `2` (in that order).
    - Secondary assertion in the **same** test: stub closure to raise `GitlabAuthenticationError(401)` → assert **no retry** (fail fast, 1 attempt, 0 sleeps).
  - `test_regression_cp1_p2_connect_retry.py::test_github_connect_retries_on_transient_and_succeeds`
    - Mirror on GitHub: `requests.exceptions.ConnectionError` × 2 then ok → 3 attempts, sleeps 1s/2s. Secondary: `BadCredentialsException` → no retry.
  - Sleep mocked via `monkeypatch.setattr("asyncio.sleep", AsyncMock())` to keep tests <100ms and to assert the backoff values directly.

---

### M.6 — `list_all_mcp_servers` sequential N+1 across tenants

- **Résumé** : GitHub `list_all_mcp_servers` and GitLab `list_all_mcp_servers` both iterate tenants with an `await self.list_mcp_servers(tenant_id)` inside a `for` loop. With 100 tenants × 1 round-trip each = 100 serial round-trips. Combined with C.1, observable latency is in the tens of seconds.
- **Fichier:ligne** : `control-plane-api/src/services/github_service.py:565-570`, `control-plane-api/src/services/git_service.py:910-929`
- **Approche de fix** : replace the `for` loop with `asyncio.gather(*[self.list_mcp_servers(tid) for tid in tenant_ids])`. Bounded concurrency is already enforced at the provider level via `GITHUB_SEMAPHORE` / `GITLAB_SEMAPHORE` inside every `_gh_read` / `_gl_run` call, so a second semaphore layer here is unnecessary. Flatten results via `list(itertools.chain.from_iterable(...))` (or nested `extend` in a loop — keep whichever reads more natural; the semantic is "merge the N per-tenant lists").
- **Régression guard proposé** :
  - `test_regression_cp1_p2_list_all_mcp_gathered.py::test_github_list_all_mcp_servers_fans_out_in_parallel`
  - `test_regression_cp1_p2_list_all_mcp_gathered.py::test_gitlab_list_all_mcp_servers_fans_out_in_parallel`
  - Scenario: stub `list_mcp_servers` with a wrapper that records invocation-order timestamps + sleeps 50ms. Call `list_all_mcp_servers` with 5 tenants → assert the wrap-around wall time < `2 × 50ms` (proves concurrency) and all 5 tenants were queried. Not a micro-benchmark — compared against a generous ceiling.

---

### L.1 — GitLab pagination silently truncates `branches.list` / `mergerequests.list`

- **Résumé** : python-gitlab's `list()` methods return page 1 (≤20 items) by default. `list_branches` and `list_merge_requests` both hit this. `list_commits` passes `per_page=limit` which bounds the first page to `limit`, but still never fetches beyond it. PyGithub pagination is transparent — this bug is GitLab-only per the Rev 2 report. Regression guards stay scoped to GitLab.
- **Fichier:ligne** :
  - `git_service.py:1124` — `project.branches.list()`
  - `git_service.py:1169` — `project.mergerequests.list(state=state)`
  - `git_service.py:792` — `project.commits.list(path=path, per_page=limit)` (borderline — see arbitration)
- **Approche de fix (corrected — option A for `list_commits`)** :
  - `list_branches` : `project.branches.list(get_all=True)`.
  - `list_merge_requests` : `project.mergerequests.list(state=state, get_all=True)`.
  - `list_commits` : `project.commits.list(path=path, per_page=min(limit, 100), iterator=True)` wrapped in `itertools.islice(..., limit)`. Preserves the existing `limit` contract while eliminating the silent truncation for `limit > 20`.
- **Régression guard proposé** :
  - `test_regression_cp1_p2_gitlab_pagination.py::test_list_branches_uses_get_all_true`
  - `test_regression_cp1_p2_gitlab_pagination.py::test_list_merge_requests_and_commits_paginate_fully`
    - One test covers `list_merge_requests` (assert `get_all=True` passed, 35 items returned) **and** `list_commits` in the same assertion block (assert `iterator=True` passed + `per_page=min(limit,100)` + the returned list honours `limit` via `islice`). Keeps the file to 2 tests per the one-per-bug rule while covering all three fixed methods.

---

## Commit plan

**Single squashed commit on `fix/cp-1-p2-batch`** — all five fixes are defensive hardening / observability / reliability, each narrow in scope. Grouping keeps the git log clean (one P2 entry to match the one-per-batch pattern set by P0/P1) and lets reviewers read the five fiches side-by-side.

Proposed commit message:

```
fix(cp-api/git): close P2 cleanup batch (5 findings)

Defensive hardening and reliability for the CP-1 GitProvider abstraction:
- M.2: merge_merge_request idempotent + single-fetch on both providers
- M.4: replace hardcoded ref="main" with settings.git.default_branch (new config)
- M.5: connect() retries with exponential backoff (1s/2s/4s, 3 attempts)
- M.6: list_all_mcp_servers fans out via asyncio.gather (both providers)
- L.1: GitLab list_branches / list_merge_requests / list_commits paginate fully

Regression guards: 10 new tests across
  test_regression_cp1_p2_merge_idempotent.py          (2)
  test_regression_cp1_p2_default_branch.py            (2)
  test_regression_cp1_p2_connect_retry.py             (2)
  test_regression_cp1_p2_list_all_mcp_gathered.py     (2)
  test_regression_cp1_p2_gitlab_pagination.py         (2)

Closes: M.2, M.4, M.5, M.6, L.1 (BUG-REPORT-CP-1.md)
```

If arbitration #2 retains the three ancillary `ref="main"` call-sites (iam_sync / deployment_orchestration / traces) in scope, they fold into the same commit (scope note already covers them).

No case justifies a second commit: none of the five forces a structural refactor. M.4 is the biggest footprint (config addition + ~25 closure-local assignments) but remains a mechanical one-pass sweep.

---

## Arbitration points

1. **Scope of M.4 sweep** — Recommend limiting to provider services (`git_service.py`, `github_service.py`) plus the three ancillary call-sites I noted (`iam_sync_service.py:210`, `deployment_orchestration_service.py:132`, `routers/traces.py:512`). **Alternative** : leave the ancillary three as-is and open a follow-up. I recommend the full sweep because the 3 extra lines are a 1-line mechanical change each, and leaving them is a foot-gun for any future refactor that drops the `ref="main"` public default.

2. **Breaking public-method defaults** — Do we also want `def get_file_content(..., ref: str | None = None)` that resolves to `settings.git.default_branch` when unset? I argue **no for this batch** — it's a public contract change with blast-radius beyond CP-1 (webMethods adapter, iam_sync, deployment_orchestration all call these with explicit `ref` today). P2 fixes the internal closures; a broader API harmonisation belongs in CP-1 follow-up or a new ticket.

3. **`list_commits` fix shape for L.1** — Two options:
   - **A** (recommended) : `per_page=min(limit, 100), iterator=True` + `islice(..., limit)` — preserves the `limit` semantics, eliminates truncation for `limit > 20`, no surprise for callers.
   - **B** (simpler) : only touch `list_branches` + `list_merge_requests`, leave `list_commits` alone. Justification: `list_commits` already honours `limit=20`, which is "bounded on purpose" for UX use-cases. The Rev 2 bug report itself flags it as "borderline". I'd accept B if you prefer to keep the diff minimal.

4. **L.1 regression test depth** — Bug report calls out "catalog repo with >20 branches or >20 MRs" as the failure case. The 2 tests I proposed stub 35 items; do you want a 3rd test explicitly demonstrating pre-fix behaviour (truncation to 20) as a recorded regression? I argue the monkeypatch on `list(get_all=True)` is already the assertion that matters — a "fail before fix" test over a stub is theatre here.

5. **L.1 follow-up for `per_page` overrides** — Should we standardise `per_page=100` on `branches.list` / `mergerequests.list` to reduce round-trips? Recommend **no** for this batch — python-gitlab defaults are fine; adding `per_page=100` is a perf tweak that doesn't belong in a cleanup batch.

---

## Risques identifiés

- **M.5 retry loop vs test startup** : if the `asyncio.sleep` is not mocked in fixtures that exercise `GitLabService().connect()` as a real side-effect (rare — most tests stub `connect` directly), test runtime could slow. Mitigation : the retry helper only sleeps on failure; passing tests never sleep. All new tests mock `asyncio.sleep`.
- **M.4 hydration ordering** : the new `GIT_DEFAULT_BRANCH` env var must be hydrated inside `_hydrate_and_validate_git` model-validator (same as `GITHUB_TOKEN` etc.) so it survives the validator reassignment of `self.git`. Otherwise the default silently stays `"main"` because the `GitProviderConfig(...)` constructor replaces the whole object.
- **M.6 parallelism and rate limits** : 100 parallel `list_mcp_servers` calls are all within `_gh_read` / `_gl_run` which serialise through the provider semaphore (10 slots). End-to-end concurrency stays capped, so no new rate-limit exposure. Just wanted to surface the reasoning.
- **L.1 fetch cost on large repos** : `get_all=True` on a GitLab project with thousands of branches / MRs will now fetch the full set. This is the **desired** behaviour (the bug was silent truncation) but callers of `list_branches` / `list_merge_requests` should expect larger payloads. The two production callers (`routers/git.py`) already paginate / filter client-side, so no UI regression expected.
- **None of the five fixes touch the sync-in-async invariant**. P0 closed the architectural split (`run_sync`), P1 closed the contract drift. P2 stays inside the closures.

---

## Global state after Phase 2 (preview)

`pytest tests/` → expect +10 tests net, 6490 total (baseline: 6480 after P0+P1).
`ruff check src/` → zero issue.
`mypy src/services/git*.py src/routers/git.py` → no regression (new field is typed, new helpers are typed).
CP-1 invariants hold:
- `grep -rn "self._project\." src/ --include="*.py" | grep -v "_test"` → 0
- `grep -rn "contextlib.suppress(Exception)" src/services/deployment_orchestration_service.py` → 0

If this batch merges as-is, **CP-1 is CLOSED** (21/21 findings : 6 P0 + 9 P1 + 5 P2 + already-closed L.2). Phase 3 will add a "CP-1 CLOSED" banner to the top of `BUG-REPORT-CP-1.md` with the commit roll-up.
