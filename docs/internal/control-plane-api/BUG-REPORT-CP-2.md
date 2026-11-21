# BUG-REPORT-CP-2 — Git provider config source of truth

## CP-2 CLOSED — 2026-04-24

**11 tracked items handled**: 9 fixed in-commit, 1 staged as patch file
(G-1 blocked by local `.env*` write guard — see `FIX-G1-env-example.patch`),
1 deferred cross-repo (C-2 → CAB-1890 GitHub flip).

| Finding | Status | Notes |
|---|---|---|
| **B-1** (P0) repr-leak | ✅ FIXED | credentials wrapped in `SecretStr` on flat ingress |
| **A-1** (P1) whitespace tokens | ✅ FIXED | `.strip()` at hydration boundary |
| **C-1** (P1) case-sensitive `GIT_PROVIDER` | ✅ FIXED | `@field_validator(mode="before")` does `strip().lower()` |
| **C-2** (P1) Helm chart GitHub env wiring | ⏩ DEFERRED | cross-repo → CAB-1890 |
| **E-1** (P2) validator identity + URL shape | ✅ FIXED | org/repo non-empty, `urlparse` for `GITLAB_URL` |
| **H-1** (P2) test fixture silent kwarg drop | ✅ FIXED | fixture uses `org`/`catalog_repo` fields |
| **H-2** (P2) conftest misleading comment | ✅ FIXED | comment reflects reality (prod is default) |
| **A-2** (P2) `_VALIDATE_GIT_CONFIG` kill-switch | ✅ FIXED | flag removed entirely |
| **G-1** (P2) `.env.example` out of sync | 📋 STAGED | `FIX-G1-env-example.patch` — user runs `git apply` (local `.env*` write guard blocks Claude Code) |
| **I-1** (P3) sub-models accept unknown kwargs | ✅ FIXED | `ConfigDict(extra="forbid")` on 3 models |
| **I-2** (P3) redundant `or "main"` | ✅ FIXED | dropped; Field default covers it |

Regression guards: 9 new tests + 1 existing-test update (SecretStr defaults).
Invariants re-verified post-fix: grep-gate green, `settings.git.*` is the
only consumer entry point, `mypy src/config.py` clean, ruff clean on
touched files.

---

Audit of `src/config.py` + consumers + tests + deployment artifacts after the
CAB-1889 CP-2 rewrite (PR #2480, commit `551bd4560`). Target module: the new
`GitProviderConfig` single-source-of-truth and `_hydrate_and_validate_git`
startup validator.

## Executive summary

- **Total findings**: 9 (1 P0 · 3 P1 · 5 P2)
- **Nothing broken by the rewrite** — migration to `settings.git.*` is clean,
  grep-gate active in CI, consumers fully cut over, 7 dead env vars dropped.
- **Top 3 risks**:
  1. **P0 · `repr(Settings)` leaks plaintext tokens**. The nine flat ingress
     fields (`GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `GITLAB_TOKEN`,
     `GITLAB_WEBHOOK_SECRET`, …) are declared `str`, not `SecretStr`.
     `exclude=True` only hides them from `model_dump()`; they remain in
     attribute access and in Pydantic's default `__repr__`. Reproduced end-to-end
     — see B-1 below.
  2. **P1 · Whitespace-only tokens silently pass the validator** in production.
     `GITHUB_TOKEN="   "` boots the app; first catalog call 401s. Single-char
     `strip()` fix.
  3. **P1 · `Literal["github", "gitlab"]` is case-sensitive** and consumers no
     longer call `.lower()`. Any existing deployment that had `GIT_PROVIDER=GITHUB`
     or `Gitlab` (pre-rewrite silently accepted) will now refuse to boot on
     first rollout. Not hypothetical — the rewrite explicitly removed the
     `.lower()` call.

None of the findings block the rewrite from staying on main. B-1 and A-1 are
worth a P0/P1 batch before the next routine prod rollout; the rest can ride
with the next cleanup sweep.

**Scope of what was checked**
- `src/config.py` (full, 566 lines) — every `Field`, validator, and the two
  `@model_validator(mode="after")` hooks.
- All 108 `settings.git*` consumer sites across `src/` (grep-gate is green).
- `tests/test_config_git_provider_validation.py`,
  `tests/test_dual_provider_smoke.py`, `tests/test_git_provider.py`,
  `tests/test_regression_cp1_token_leak.py`, `tests/conftest.py`.
- Deployment artifacts: `.env.example`, `k8s/configmap.yaml`,
  `charts/stoa-platform/values.yaml`,
  `stoa-infra/charts/control-plane-api/{values,templates/deployment}.yaml`.
- `scripts/check_git_config_access.sh` + CI gate in
  `.github/workflows/control-plane-api-ci.yml:50-66`.

Explicitly out of scope (not bugs, risks tracked elsewhere):
- R-1 singleton `git_service = GitLabService()` at `git_service.py:1396` —
  REWRITE-PLAN §F defers to CP-3.
- `_project` leak cleanup in `iam_sync_service.py` / `deployment_orchestration_service.py` —
  shipped (regression markers confirmed `iam_sync_service.py:205`,
  `deployment_orchestration_service.py:102`).
- CP-1 findings (BUG-03, BUG-05, BUG-06 in `REWRITE-BUGS.md`) — unrelated
  to CP-2 scope.

---

## Critical (P0)

### B-1 — `repr(Settings)` leaks plaintext tokens and webhook secrets

**Category**: D — security (token logging)
**File**: `src/config.py:141-149`
**Reproduction** (confirmed):

```python
import os
os.environ['GIT_PROVIDER'] = 'github'
os.environ['GITHUB_TOKEN'] = 'ghp_realsecret_MUST_NOT_LEAK_123456789'
os.environ['GITHUB_WEBHOOK_SECRET'] = 'whsec_very_secret_456'
os.environ['ENVIRONMENT'] = 'production'
from src.config import Settings
s = Settings()
r = repr(s)
# → GITHUB_TOKEN='ghp_realsecret_MUST_NOT_LEAK_123456789', GITHUB_WEBHOOK_SECRET='whsec_very_secret_456'
```

**Root cause**: the nine flat ingress fields are typed `str`, not `SecretStr`.
The `exclude=True` keyword only filters `model_dump()` / `model_dump_json()` —
it does not hide the field from attribute access nor from Pydantic's default
`__repr__`. Only the *hydrated* `settings.git.github.token` is a `SecretStr`
(wrapped at line 476), so the secrets live in memory twice: once masked, once
plaintext.

**Attack surface** (theoretical):
- Any `logger.debug(f"config={settings}")`, unhandled exception capturing
  `self.settings` in its locals dict, or a future diagnostic endpoint that
  happens to `str(settings)` will emit the token. The `SecretRedactor` root
  log filter (`main.py:157-160`) is defense-in-depth — it regex-matches `ghp_`
  and `glpat-` prefixes, but does **not** cover custom tokens (enterprise
  GitHub tokens, PAT formats that aren't the GitHub pattern, webhook
  secrets with no fixed prefix).

**Exploitable today**: no caller currently `repr()`s `settings`. But the field
is a live plaintext copy — the rewrite explicitly wanted secrets wrapped at
the boundary, and the boundary here is the flat ingress field.

**Fix direction**: declare the four credential flat fields as `SecretStr`:
```python
GITHUB_TOKEN: SecretStr = Field(default=SecretStr(""), exclude=True)
GITHUB_WEBHOOK_SECRET: SecretStr = Field(default=SecretStr(""), exclude=True)
GITLAB_TOKEN: SecretStr = Field(default=SecretStr(""), exclude=True)
GITLAB_WEBHOOK_SECRET: SecretStr = Field(default=SecretStr(""), exclude=True)
```
Update the hydrator at lines 474-488 to call `.get_secret_value()` when
unwrapping into the SecretStr at the inner model boundary (or just pass the
SecretStr through — the SecretStr chains).

**Regression test**: `repr(Settings(...))` must not contain the raw token
string. Ideally assert on `'ghp_'`, `'glpat-'`, and `'whsec_'` prefixes.

---

## High (P1)

### A-1 — Whitespace-only tokens silently pass the validator

**Category**: A — startup validation gap
**File**: `src/config.py:498-509`
**Reproduction** (confirmed):

```python
os.environ['GIT_PROVIDER'] = 'github'
os.environ['GITHUB_TOKEN'] = '   '        # 3 spaces
os.environ['ENVIRONMENT'] = 'production'
Settings()  # passes — should raise
```

The validator uses `if not git.github.token.get_secret_value()` (falsy check).
Python `bool("   ") is True`, so whitespace-only strings slip through. Same
applies to `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, and trailing-newline secrets
from K8s file-mounted secrets (`echo -n` omitted in the manifest → trailing
`\n` in the decoded value).

**Why it matters**: K8s Secret mounts that were populated via `kubectl create
secret generic --from-file=token=…` include the file's trailing newline. A
token pasted into a Helm value with a stray space at the end survives today.
Runtime failure mode is a cryptic 401 from GitHub/GitLab rather than the
clear "refusing to boot" message the validator is supposed to give.

**Fix direction**: swap `not token.get_secret_value()` for
`not token.get_secret_value().strip()`. Apply the `.strip()` at the
hydration boundary (lines 473-488) so every downstream consumer sees the
normalised value — otherwise the provider client still receives the
whitespace and fails.

**Regression test**: add two cases to
`tests/test_config_git_provider_validation.py::TestProductionValidationCrashes`:
`GITHUB_TOKEN="   "` and `GITHUB_TOKEN="token\n"` — both should raise
`ValidationError("empty")`.

---

### C-1 — Mixed-case `GIT_PROVIDER` now crashes on boot (backward compat regression)

**Category**: C — backward compat
**File**: `src/config.py:141` (`Literal["github", "gitlab"]`) + consumer
migration in `src/services/git_provider.py:426` (pre-rewrite used
`.lower()`).
**Reproduction** (confirmed):

```python
os.environ['GIT_PROVIDER'] = 'GitHub'  # mixed case
Settings()
# pydantic_core._pydantic_core.ValidationError:
# GIT_PROVIDER Input should be 'github' or 'gitlab' [type=literal_error, input_value='GitHub']
```

Before the rewrite, `git_provider_factory()` did
`settings.GIT_PROVIDER.lower()` so `"GITHUB"`, `"GitLab"`, etc. were all
accepted. The rewrite removed the `.lower()` (REWRITE-PLAN §C.2#4) because
`Literal` guarantees casing — which means any ConfigMap/Helm value that
happened to carry uppercase now blocks startup.

**Blast radius**: unknown without scanning every historical override. The
only confirmed usage is `stoa-infra/charts/control-plane-api/values.yaml:11`
(`GIT_PROVIDER: gitlab` — lowercase, safe). But self-hosted quickstart
users, external customers, or ancient dev `.env` files may carry uppercase.
There is no migration note in the CHANGELOG warning ops.

**Fix direction**: either
- (preferred, documented) keep `Literal["github", "gitlab"]`, add a CHANGELOG
  breaking-change note + a migration warning in the rewrite PR description,
  and leave it; *or*
- re-introduce a `@field_validator("GIT_PROVIDER", mode="before")` that
  lowercases the raw env value before Literal narrowing. One-liner fix that
  preserves compat forever at almost no cost:
  ```python
  @field_validator("GIT_PROVIDER", mode="before")
  @classmethod
  def _normalise_provider_case(cls, v: str) -> str:
      return v.lower() if isinstance(v, str) else v
  ```

**HYPOTHÈSE À VÉRIFIER**: I have not enumerated every prod/staging deployment.
If a `helm get values` sweep confirms all deployments are lowercase, this
drops to P2 (ops documentation only). If *any* deployment had uppercase,
this is P1 and blocks the next rollout.

---

### C-2 — Helm chart cannot run `GIT_PROVIDER=github` in prod (cross-repo)

**Category**: C — backward compat (operational)
**File**: `stoa-infra/charts/control-plane-api/templates/deployment.yaml:34-83`
(NOT in this repo; cross-repo finding)

The chart passes only six Git env vars to the container:
- `GIT_PROVIDER`, `GITLAB_URL` (from `values.env`)
- `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `GITLAB_WEBHOOK_SECRET` (from `gitlabSecret`)

The four GitHub env vars (`GITHUB_TOKEN`, `GITHUB_ORG`,
`GITHUB_CATALOG_REPO`, `GITHUB_WEBHOOK_SECRET`) and the new
`GIT_DEFAULT_BRANCH` are **not wired**. Flipping `GIT_PROVIDER: github` in
`values.yaml` would now cause the validator to raise `GITHUB_TOKEN is empty`
and crash-loop the pod, with no obvious hint to ops that the chart is
incomplete.

This is documented in REWRITE-PLAN as R-5 ("prod reste gitlab, flip vers
github = CAB-1890"). Noting here so the CP-2 audit paper-trail captures it:
the rewrite's startup validator turned what used to be a silent misconfig
(runtime 401) into a hard crash, which surfaces the missing chart wiring as
an operational incident rather than a latent bug. That's an improvement —
just one that arrives before the chart catches up.

**Fix direction**: open a `stoa-infra` PR that:
1. Adds `GITHUB_*` env passthrough and a `githubSecret` Helm value analogous
   to `gitlabSecret`.
2. Adds `GIT_DEFAULT_BRANCH` env passthrough (currently hard-defaults to
   `"main"` via the config).
3. Leaves `GIT_PROVIDER: gitlab` default in `values.yaml` so nothing changes
   for existing installs.

Alternatively, gate on CAB-1890 which already owns the GitHub flip.

---

## Medium (P2)

### E-1 — Validator only checks tokens + `GITLAB_PROJECT_ID`; other required fields unchecked

**Category**: E/A — partial validation
**File**: `src/config.py:497-514`
**Reproduction**:

```python
os.environ['GIT_PROVIDER'] = 'github'
os.environ['GITHUB_TOKEN'] = 'ghp_valid'
os.environ['GITHUB_ORG'] = ''           # empty
os.environ['GITHUB_CATALOG_REPO'] = ''  # empty
os.environ['ENVIRONMENT'] = 'production'
Settings()  # passes
# → settings.git.github.catalog_project_id == '/' (malformed)
```

`GITHUB_ORG` and `GITHUB_CATALOG_REPO` default to non-empty strings, so the
common case is fine, but explicit overrides to empty values survive
validation and produce a malformed `org/repo` slug (`"/"`) that breaks
downstream `github_service.py:838`. Same class of issue for `GITLAB_URL=""`
or `GITLAB_URL="not a url"`.

**Fix direction**: tighten the validator to assert non-empty-after-strip
for the selected provider's required identity fields:
- github: `GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_CATALOG_REPO`
- gitlab: `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `GITLAB_URL` (plus a URL shape
  check — `urllib.parse.urlparse(url).scheme in {"https", "http"}`)

Low-urgency because the default values are sensible; only surfaces on
explicit empty override.

---

### H-1 — Test helper `_patched_git_settings` silently drops `catalog_project_id` kwarg

**Category**: H — test intent/behaviour divergence
**File**: `tests/test_regression_cp1_token_leak.py:66-68`

```python
return GitProviderConfig(
    provider="github",
    github=GitHubConfig(
        token=SecretStr(token),
        catalog_project_id="org/catalog",   # ← silently ignored
        webhook_secret=SecretStr("whsec"),
    ),
)
```

`GitHubConfig.catalog_project_id` is a `@property`
(`src/config.py:45-48`), not a field. Pydantic `BaseModel`'s default
`extra="ignore"` drops the unrecognised kwarg without warning, so the test
fixture is configured with the *default* catalog (`"stoa-platform/stoa-catalog"`)
rather than the intended `"org/catalog"`. Verified end-to-end:

```python
g = GitHubConfig(token=SecretStr('t'), catalog_project_id='org/catalog', webhook_secret=SecretStr('w'))
# org='stoa-platform', catalog_repo='stoa-catalog',
# catalog_project_id='stoa-platform/stoa-catalog'   ← not 'org/catalog'
```

**Why it matters**: the test file is a security regression suite (token
leak scenarios). The affected tests don't assert on the catalog value
directly, so they still pass — but the fixture's intent is wrong, and the
pattern is copy-pasteable into future tests that *do* rely on the catalog
identity. This is the kind of silent fixture drift that hides bugs for
months.

**Fix direction**: two complementary changes.
1. Fix the fixture (P2): override the underlying fields —
   ```python
   github=GitHubConfig(token=SecretStr(token), org="org", catalog_repo="catalog", …)
   ```
2. Prevent recurrence (P3): add `model_config = ConfigDict(extra="forbid")`
   on `GitHubConfig`, `GitLabConfig`, `GitProviderConfig` so any future
   typo explodes loudly at test time.

---

### H-2 — `conftest.py` comment claims tests don't run under `ENVIRONMENT=production`, but they do

**Category**: H — test setup fragility
**File**: `tests/conftest.py:40-47`

Quoted comment: *"Tests do not run under `ENVIRONMENT=production`, so this
only avoids the dev-mode warning spam during the suite."*

Verified false: `Settings.ENVIRONMENT` defaults to `"production"` (config.py:92),
conftest does **not** override it (no `os.environ.setdefault("ENVIRONMENT", "dev")`),
pytest config has no env injection, and no `pytest_plugins` set it either.
The suite has been running under production semantics all along — which is
why the `_hydrate_and_validate_git` + `_gate_sensitive_debug_flags_in_prod`
validators both fire their prod branch. The conftest's
`GITLAB_TOKEN=test-token` + `GITLAB_PROJECT_ID=1` is exactly what keeps
the git validator quiet; if either were missing, the whole suite would
crash at `from src.config import Settings`.

**Why it matters**: when a future dev adds a new prod-gated invariant
and the suite crashes unexpectedly, the conftest comment misleads the
debugger. Tests that *need* non-prod env explicitly set it via
`Settings(ENVIRONMENT="dev")` or `monkeypatch.setenv` — the global
default is incidental and load-bearing.

**Fix direction**: either
- set `os.environ.setdefault("ENVIRONMENT", "test")` in conftest
  alongside the git defaults (document "test" as a non-production sentinel
  that dev/staging branches treat identically to dev); *or*
- fix the comment to say "tests run as production by default; we set the
  gitlab creds so the validator is satisfied".

Second option is lower risk — changing the env at test scope could
silently reshape validator behaviour for dozens of tests.

---

### G-1 — `.env.example` out of sync with `Settings` (9 Git vars)

**Category**: G / C — operational doc drift
**File**: `.env.example:80-83`

Current state:
```ini
# ── GitLab (optional, for UAC catalog sync) ──────────────────────────────────
# GITLAB_URL=https://gitlab.com
# GITLAB_TOKEN=
# GITLAB_PROJECT_ID=
```

Missing: `GIT_PROVIDER`, `GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_CATALOG_REPO`,
`GITHUB_WEBHOOK_SECRET`, `GITLAB_WEBHOOK_SECRET`, `GIT_DEFAULT_BRANCH`.
REWRITE-PLAN §C.4 called for an explicit "Git Provider" section covering all
nine. The merging PR description notes this was blocked by a local `.env*`
write guard and flagged as "needs manual follow-up commit". That commit
hasn't landed.

**Why it matters**: a new self-hoster follows `.env.example`, never sees
`GIT_PROVIDER`, takes the default (`github`), and crashes on boot because
`GITHUB_TOKEN` is empty. The new prod validator makes the failure loud
(good), but the root cause is documentation debt.

**Fix direction**: append the missing section, keeping all lines commented
so existing self-hosted setups are unaffected:
```ini
# ── Git Provider (UAC catalog sync) — CAB-1889 CP-2 ──────────────────────────
# GIT_PROVIDER=github           # github | gitlab
# GIT_DEFAULT_BRANCH=main
# GITHUB_TOKEN=
# GITHUB_ORG=stoa-platform
# GITHUB_CATALOG_REPO=stoa-catalog
# GITHUB_WEBHOOK_SECRET=
# GITLAB_URL=https://gitlab.com
# GITLAB_TOKEN=
# GITLAB_PROJECT_ID=
# GITLAB_WEBHOOK_SECRET=
```

---

### A-2 — `_VALIDATE_GIT_CONFIG` kill-switch has no guardrail test

**Category**: A / G — startup validation hygiene
**File**: `src/config.py:34`, `src/config.py:491-492`

```python
_VALIDATE_GIT_CONFIG: bool = True
...
if not _VALIDATE_GIT_CONFIG:
    return self
```

A one-line flip of this module-level constant disables all Git prod
validation silently. There is **no test** asserting the flag is `True`, and
no CI check. If a future "hotfix" flips it to `False` to quiet a noisy boot
warning on a rollout, the guard is gone and nobody notices.

**Why it matters**: the flag was supposed to be a migration scaffold
(REWRITE-PLAN §C.1 called for flipping it in C.3 once consumers migrated).
C.3 flipped it on the same commit; the flag now has no purpose. Leaving it
as a live toggle is a foot-gun.

**Fix direction**: either
- remove the flag entirely (inline the validation; the consumers are
  all migrated — the grep-gate in CI enforces this); or
- keep it and add a regression test
  `tests/test_config_git_provider_validation.py::test_validation_flag_is_on`:
  ```python
  from src.config import _VALIDATE_GIT_CONFIG
  assert _VALIDATE_GIT_CONFIG is True, "Git validation must stay on in prod builds"
  ```

Preferred: remove. The flag has done its job.

---

## Low (P2/P3 — informational)

### I-1 — `GitHubConfig` / `GitLabConfig` / `GitProviderConfig` accept arbitrary kwargs

**Category**: H — design hygiene
**File**: `src/config.py:37`, `src/config.py:51`, `src/config.py:64`

None of the three sub-models declare `model_config = ConfigDict(extra="forbid")`.
Pydantic `BaseModel` default is `extra="ignore"`, so a typo like
`GitHubConfig(tokne=...)` is silently discarded. Not a bug today (no caller
has a typo), but it's the mechanism that enabled H-1 to slip past review.

**Fix direction**: add `model_config = ConfigDict(extra="forbid")` to all
three models. Matches the intent of "source of truth" — unknown keys
should raise.

---

### I-2 — `default_branch=self.GIT_DEFAULT_BRANCH or "main"` redundant fallback

**Category**: cosmetic (not a bug)
**File**: `src/config.py:487`

```python
default_branch=self.GIT_DEFAULT_BRANCH or "main",
```

`GIT_DEFAULT_BRANCH` is declared `Field(default="main")`, so `self.GIT_DEFAULT_BRANCH`
is never the empty string unless someone explicitly sets
`GIT_DEFAULT_BRANCH=""` in env. In that corner case, the `or "main"` silently
overrides the operator's explicit empty choice — arguably a footgun, but
more likely just dead code.

**Fix**: drop the `or "main"` — let the operator's choice stand and let
downstream fail loudly if the branch doesn't exist.

---

## Scope — notes de design (non-bugs)

- **`settings.git.provider` vs `GIT_PROVIDER` at startup**: the singleton
  `git_service = GitLabService()` at `git_service.py:1396` still runs a
  GitLab connect in the FastAPI lifespan regardless of `GIT_PROVIDER`. This
  is the R-1 risk explicitly deferred to CP-3 — not a CP-2 regression.
  Confirmed `iam_sync_service.py:205` and `deployment_orchestration_service.py:102`
  now go through the provider-agnostic ABC (regression markers present), so
  the leak is walled off to the one lifespan call.
- **`Literal` case-sensitivity**: covered by C-1 but worth noting that the
  CHANGELOG for this rewrite should carry a breaking-change note even if
  the `.lower()` shim is re-introduced, because downstream catalogues or
  tests that string-matched `"GitLab"` may also break.
- **SecretStr shared default**: `Field(default=SecretStr(""))` reuses one
  `SecretStr` instance across all default-constructed models. Safe because
  `SecretStr` is effectively immutable — mentioned only because it's the
  kind of thing that trips code reviews.
- **`get_git_provider()` `lru_cache`** at `git_provider.py:443` caches the
  factory output for the process lifetime. Tests clear the cache via
  `get_git_provider.cache_clear()` — correct. Not a bug, but worth being
  aware that `settings.git.provider` changes at runtime (which shouldn't
  happen — it's env-set at boot) would *not* rebuild the cached provider.

---

## Priorité de fix suggérée

1. **B-1** (P0) — wrap flat credential fields in `SecretStr`. Single-file
   change, tests should drive it (`repr(Settings(...))` must not contain
   token/webhook secret values). ~30 min.
2. **A-1** (P1) — `.strip()` the token + project-id at the hydration
   boundary. Two regression tests. ~15 min.
3. **C-1** (P1) — decide: keep strict `Literal` + add CHANGELOG + ops
   comms, OR add the `mode="before"` lowercasing field validator. Either
   way, get a PR out before the next prod rollout. ~15 min + comms.
4. **C-2** (P1) — cross-repo `stoa-infra` follow-up for GitHub env
   passthrough. Pair with CAB-1890 since that ticket already owns the
   GitHub flip. ~1h.
5. **E-1** (P2) — tighten validator to cover `GITHUB_ORG` / `GITHUB_CATALOG_REPO`
   + URL shape. ~20 min.
6. **G-1** (P2) — `.env.example` section append. Write-guard unlock or
   manual edit. ~5 min.
7. **H-1** + **I-1** (P2/P3) — test fixture fix + `extra="forbid"`. ~15 min.
8. **H-2** (P2) — conftest comment fix (or the more ambitious env default
   set). ~5 min.
9. **A-2** (P2) — remove `_VALIDATE_GIT_CONFIG` flag (or add its guardrail
   test). ~10 min.

Total estimated IA time for everything P0+P1+P2: **under 3h**. Under 1h if
C-2 is deferred to the CAB-1890 track.

---

**Audit end — phase 1 (no fixes applied). Awaiting triage.**
