# FIX-PLAN-CP2 — All-in-One close of CP-2 bug hunt (9 findings)

> **Scope**: 1 atomic commit on `fix/cp-2-bug-hunt-batch` branched from fresh
> `main`. Total est. ≤ 3h IA time. Branching from `main` is mandatory — current
> session sits on `fix/gw-1-p2-batch` (GW-1 PR #2512 still open), so Phase 2
> must start with `git fetch origin && git switch main && git pull && git
> switch -c fix/cp-2-bug-hunt-batch`.

Ref: `control-plane-api/BUG-REPORT-CP-2.md` for the finding-by-finding
write-up.

---

## A. Ordre d'exécution dans le commit

All 10 edits (9 findings + explicit C-2 trace in commit body) land in one
commit. Within that commit, edits are applied in an order that keeps each
step locally coherent — so if Phase 2 is interrupted and diffs are inspected
mid-flight, nothing mid-edit looks broken.

| # | Item | File | Depends on | Notes |
|---|------|------|------------|-------|
| 1 | **H-1** fix test fixture first | `tests/test_regression_cp1_token_leak.py` | — | Replace silently-dropped `catalog_project_id=` kwarg with `org="org", catalog_repo="catalog"`. Must land **before** step 2. |
| 2 | **I-1** `extra="forbid"` on 3 sub-models | `src/config.py` | #1 | Without #1 first, this step would make the test fixture crash. |
| 3 | **B-1** wrap 4 credential flat fields in `SecretStr` | `src/config.py` | — | Types change for `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `GITLAB_TOKEN`, `GITLAB_WEBHOOK_SECRET`. Updates hydrator lines 475-488. |
| 4 | **A-1** `.strip()` at hydration boundary | `src/config.py` | #3 | Chain `.get_secret_value().strip()` then re-wrap in SecretStr. Applies to tokens + webhook secrets + `GITLAB_PROJECT_ID`. |
| 5 | **C-1** `@field_validator("GIT_PROVIDER", mode="before")` | `src/config.py` | — | Lowercase raw value before Literal narrowing. Restores pre-rewrite backward compat. |
| 6 | **E-1** tighten validator (org/repo/url) | `src/config.py` | #3/#4 | New checks inside `_hydrate_and_validate_git`: non-empty after strip for org + repo; URL shape check for `GITLAB_URL`. |
| 7 | **A-2** remove `_VALIDATE_GIT_CONFIG` kill-switch | `src/config.py` + `tests/conftest.py` | — | Delete the module constant + the `if not _VALIDATE_GIT_CONFIG: return self` guard; update conftest comment that still mentions the flag. Grep-verified: no other reference in code. |
| 8 | **I-2** drop redundant `or "main"` | `src/config.py` | — | One-line change at the `default_branch=…` site. |
| 9 | **G-1** sync `.env.example` | `control-plane-api/.env.example` | — | Append explicit Git Provider section (9 vars, all commented). |
| 10 | **H-2** fix conftest comment | `tests/conftest.py` | #7 | Merge with step #7's conftest edit — both touch the same comment block. |

**All 8 regression guards** (see §C) added alongside the production code in
the same commit.

---

## B. Arbitrages à résoudre

### B.1 — B-1 hydrator path after SecretStr wrap

The current hydrator wraps the plain `str` fields in `SecretStr` at
`src/config.py:475-488`:

```python
token=SecretStr(self.GITHUB_TOKEN),
```

After B-1, `self.GITHUB_TOKEN` is itself a `SecretStr`. Double-wrapping
(`SecretStr(SecretStr(...))`) is invalid. We also need A-1's `.strip()`.
The minimal coherent shape:

```python
token=SecretStr(self.GITHUB_TOKEN.get_secret_value().strip()),
```

This:
- unwraps the SecretStr once,
- strips whitespace/newlines (A-1),
- re-wraps at the inner-model boundary.

`GITHUB_ORG`, `GITHUB_CATALOG_REPO`, `GITLAB_URL`, `GITLAB_PROJECT_ID`,
`GIT_DEFAULT_BRANCH` stay `str`. Apply `.strip()` to them too (cheap, fixes
K8s mount newlines for non-secrets).

**Decision**: pass all string inputs through `.strip()`; re-wrap only the
four credential ones in `SecretStr`. No other touch of the inner models
needed.

### B.2 — C-1 field_validator location

`@field_validator("GIT_PROVIDER", mode="before")` on `Settings` is correct:

- `mode="before"` runs prior to Literal narrowing, so `"GITHUB"` → `"github"`
  before the `Literal["github", "gitlab"]` check fires.
- Guard for non-str inputs (defensive; Pydantic may pass a default or
  kwarg-typed value): `return v.lower() if isinstance(v, str) else v`.
- Located right after the credential field declarations (after line 154) so
  anyone reading `Settings` sees the normalisation next to the field.

No need to touch the inner `GitProviderConfig.provider` Literal — the flat
ingress is the only ingestion path.

### B.3 — H-2 conftest choice

Two options:

- **Option A (recommended)**: fix the comment. Change the false claim to
  the actual mechanism. Zero behavioural risk.
  > "Tests run under `ENVIRONMENT=production` by default (Settings default).
  > We set gitlab creds here so `_hydrate_and_validate_git` is satisfied and
  > the suite imports `src.config` without crashing."

- **Option B**: `os.environ.setdefault("ENVIRONMENT", "test")` and make the
  validators treat `"test"` like `"dev"`. Broader blast radius — any test
  that indirectly relied on prod-gated behaviour (the CORS origins
  stripper, the sensitive debug flag gate, the git validator) would flip.

**Decision**: Option A. Matches BUG-REPORT recommendation. Bundle the
comment fix with the A-2 edit since both touch the same conftest block.

### B.4 — A-2 suppression vs guardrail test

Grep audit before Phase 2:

| Location | Kind | Action |
|----------|------|--------|
| `src/config.py:34` | declaration | delete |
| `src/config.py:468` | docstring mention in validator | rephrase (remove "when _VALIDATE… is True") |
| `src/config.py:491-492` | `if not _VALIDATE_GIT_CONFIG: return self` | delete |
| `tests/conftest.py:41` | comment reference | rephrase (bundle with H-2) |
| `REWRITE-PLAN.md` / `BUG-REPORT-CP-2.md` | historical docs | leave untouched (they document the migration) |

No test imports the flag. No runtime code outside `config.py` references it.
**Safe to delete outright.**

### B.5 — C-2 trace format in commit body

Already mirrored in the user-provided Phase 2 template:

> ```
> Deferred cross-repo:
> - C-2 (P1): stoa-infra Helm chart needs GITHUB_* env passthrough.
>   Tracked under CAB-1890 (GitHub flip).
> ```

Confirmed this is sufficient — CAB-1890 already owns the GitHub flip, so
pairing the chart wiring with it is natural.

---

## C. Régression guards (8 new tests)

All in `tests/test_config_git_provider_validation.py` (extend existing
classes) except the fixture test which belongs in
`tests/test_regression_cp1_token_leak.py` and the `extra="forbid"` test
which belongs in `tests/test_git_provider.py` next to `TestGitProviderConfig`.

| # | Test | File / location | Asserts |
|---|------|-----------------|---------|
| 1 | `test_repr_settings_does_not_leak_tokens` | `test_config_git_provider_validation.py` | `repr(Settings(...))` with `GITHUB_TOKEN=ghp_x`, `GITHUB_WEBHOOK_SECRET=whsec_y`, `GITLAB_TOKEN=glpat_z`, `GITLAB_WEBHOOK_SECRET=whsec_w` never contains any of those literals |
| 2 | `test_whitespace_only_token_rejected` | same | `GITHUB_TOKEN="   "` + prod → `ValidationError` matching "empty" |
| 3 | `test_trailing_newline_token_stripped` | same | `GITHUB_TOKEN="ghp_x\n"` + prod → `Settings()` succeeds AND `settings.git.github.token.get_secret_value() == "ghp_x"` (stripped) |
| 4 | `test_git_provider_accepts_mixed_case` | same | `GIT_PROVIDER="GitHub"` with full github creds + prod → `settings.git.provider == "github"` |
| 5 | `test_github_org_empty_rejected` | same | `GITHUB_ORG=""` + github + token + prod → `ValidationError` mentioning `GITHUB_ORG` |
| 6 | `test_invalid_gitlab_url_rejected` | same | `GITLAB_URL="not-a-url"` + gitlab + token + project_id + prod → `ValidationError` mentioning `GITLAB_URL` shape |
| 7 | `test_fixture_uses_correct_github_org` | `test_regression_cp1_token_leak.py` | New test; builds via `_patched_git_settings("github", "ghp_x")`, asserts `cfg.github.org == "org"` and `cfg.github.catalog_repo == "catalog"` — proves the fixture fix landed |
| 8 | `test_githubconfig_rejects_unknown_kwargs` | `test_git_provider.py` under `TestGitProviderConfig` | `GitHubConfig(tokne=SecretStr("x"))` raises `ValidationError`; same for `GitLabConfig` and `GitProviderConfig` |

**No dedicated test** for the trivial items:
- G-1 (`.env.example`): content-only, no runtime effect.
- H-2 (conftest comment): pure doc.
- A-2 (flag removal): coverage already provided by existing
  `TestProductionValidationCrashes` — if the flag were re-introduced and
  flipped off, those tests would start passing despite bad creds → caught.
- I-2 (redundant `or "main"`): existing `default_branch` tests cover it.

**Existing test updates required** (not net-new):

- `tests/test_git_provider.py:115-118` — asserts
  `Settings.model_fields["GITHUB_TOKEN"].default == ""`. After B-1 the
  default becomes `SecretStr("")`, so the assertion must change to
  `.default.get_secret_value() == ""`. Same for
  `GITHUB_WEBHOOK_SECRET`. This is a 2-line edit; include it in the commit.

---

## D. Risques identifiés

### D.1 — H-1 ordering vs I-1

Already folded into §A order (H-1 step #1, I-1 step #2). Without this
order, the `tests/test_regression_cp1_token_leak.py` fixture would crash at
collection time once `extra="forbid"` lands.

### D.2 — C-1 silent breaking-change masked

Adding the `.lower()` field_validator restores backward compat — but it
also hides from future readers that the Literal is case-sensitive. A
reader who sets `GIT_PROVIDER=GITHUB` in a test kwarg `Settings(GIT_PROVIDER="GITHUB")`
will get it normalised, not rejected. Acceptable trade-off; mention in the
commit message so the behaviour is search-grep-able.

### D.3 — A-2 removal beyond grep's reach

Grep in §B.4 covers all in-tree refs. Out-of-tree ops tooling (ansible
playbooks in stoa-infra, runbook snippets in stoa-docs) may mention the
flag name. I checked `stoa-infra/charts/control-plane-api/` — no mention.
stoa-docs: out of audit scope, but the flag has never been documented
user-facing (it was a migration scaffold). **Low residual risk.**

### D.4 — B-1 flat `SecretStr` defaults + Pydantic Settings env ingestion

Declaring `GITHUB_TOKEN: SecretStr = Field(default=SecretStr(""), exclude=True)`:

- Env var ingestion: `pydantic-settings` v2 auto-wraps a plain string env
  value into `SecretStr` at field validation — confirmed by existing
  `GitHubConfig.token: SecretStr` usage in the rewrite. **No ingestion
  regression.**
- Default-factory concern: `Field(default=SecretStr(""))` shares one
  `SecretStr("")` instance across all default-constructed `Settings()`
  — safe because `SecretStr` is effectively immutable.
- Tests that patch `settings.GITHUB_TOKEN = "x"` would break (type
  mismatch). **Grep confirms zero such patches** in `tests/` — everyone
  goes via `monkeypatch.setenv` (string env var, auto-wrapped) or via
  `mock_settings.git.github.token = SecretStr(...)`.

### D.5 — E-1 URL validation scope

The URL shape check for `GITLAB_URL` should be tolerant:
- Accept `http://` and `https://` schemes.
- Non-empty netloc required.
- No deep path/query validation (gitlab.com works; self-hosted
  `https://gitlab.corp/path/subpath/` also works).

Use `urllib.parse.urlparse`. Only raise when both scheme is `http(s)` and
netloc is empty, or scheme is unset entirely. Err on the side of permissive
so valid self-hosted URLs aren't rejected.

---

## E. Commit message

```
fix(cp-api/config): close CP-2 bug hunt batch (9 findings)

Security, validation and hygiene fixes on GitProviderConfig source of truth:
- B-1 (P0): wrap credentials in SecretStr to prevent repr() leak
- A-1 (P1): strip whitespace/newlines on tokens at hydration boundary
- C-1 (P1): field_validator restores case-insensitive GIT_PROVIDER for compat
- E-1 (P2): tighten validator on GITHUB_ORG, GITHUB_CATALOG_REPO, GITLAB_URL
- G-1 (P2): sync .env.example with full Git Provider section
- H-1 (P2): fix test fixture to use correct GitHubConfig fields
- H-2 (P2): correct misleading conftest comment
- A-2 (P2): remove _VALIDATE_GIT_CONFIG kill-switch (migration done)
- I-1 (P3): extra="forbid" on Git* sub-models prevents silent kwarg drop
- I-2 (P3): remove redundant `or "main"` fallback

Regression guards: 8 new tests covering repr-leak, whitespace rejection,
trailing-newline normalisation, case-insensitive GIT_PROVIDER, empty-field
rejection, URL shape, fixture correctness, extra="forbid".

Deferred cross-repo:
- C-2 (P1): stoa-infra Helm chart needs GITHUB_* env passthrough.
  Tracked under CAB-1890 (GitHub flip).

Module CP-2 CLOSED — 9/9 findings handled (1 P0 + 2 P1 + 5 P2 + 2 P3 +
1 deferred).

Closes: B-1, A-1, C-1, E-1, G-1, H-1, H-2, A-2, I-1, I-2 (BUG-REPORT-CP-2.md)
Deferred: C-2 → CAB-1890
```

Note: the header count in the report summary will be updated to match
(1 P0 + 2 P1 fixed + 1 P1 deferred + 5 P2 + 2 P3 = 10 items; findings
are labelled 9 in the report because I-1/I-2 were listed together as
"Low" — I'll reconcile that in the report header so it reads as "10/10
findings handled, 9 in-scope fixed + 1 cross-repo deferred".

---

## F. Phase 3 validation checklist

1. `pytest tests/ -x -v` — all green incl. 8 net-new tests + 1 existing-test update.
2. `ruff check src/` — clean.
3. `mypy src/config.py` — no new errors.
4. CP-2 invariant: `grep -rn "os\.getenv.*\(GITHUB\|GITLAB\|GIT_PROVIDER\)" src/ --include="*.py" | grep -v "src/config.py"` → empty.
5. `bash scripts/check_git_config_access.sh src` → "OK: no direct access".
6. Smoke: `GITHUB_TOKEN="   " python -c "from src.config import Settings; Settings()"` → `ValidationError`.
7. Smoke: `python -c "import os; os.environ.update({'GIT_PROVIDER':'github','GITHUB_TOKEN':'ghp_x','ENVIRONMENT':'production'}); from src.config import Settings; s=Settings(); assert 'ghp_x' not in repr(s)"` → exits 0.
8. Smoke: `GIT_PROVIDER=GitHub python -c "from src.config import Settings; print(Settings().git.provider)"` → prints `github`.
9. Update `BUG-REPORT-CP-2.md`:
   - Add "## CP-2 CLOSED" block at the top (date, commit SHA, 9 FIXED + 1 DEFERRED summary).
   - Annotate each finding section with `**Status**: FIXED — commit <sha>` or `**Status**: DEFERRED — CAB-1890`.
10. Final recap: commit SHA + per-finding status.

**Phase 2 starts only after explicit validation of this plan.**
