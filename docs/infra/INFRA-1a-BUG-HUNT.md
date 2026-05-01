# INFRA-1a Phase 2 Bug Hunt — Findings

**Status**: Bug Hunt complete, dispositions tightened post-review. Awaiting
Christophe arbitrage on Phase 3 batching.
**Source**: HEG-PAT-020 §5 systematic audit on PRs A→E (CAB-2199).
**Branch**: `audit/infra-1a-phase-2-bug-hunt` from `main`.
**Date**: 2026-05-01 (revision v2 — disposition matrix rewritten from
DEFERRED/WONT-FIX into FIX-NOW/FOLLOW-UP/ACCEPTED; Phase 3 batching).

> Per HEG-PAT-020 §5 discipline: this audit document is the only deliverable
> in the audit branch. No code change is committed here. Fixes ship in
> Phase 3 micro-PRs per the batching in §3.

---

## Scope recap

The audit targets the code touched by CAB-2199 Phase 2 (PRs A→E, 5 micro-PRs
merged 2026-04-30):

- `control-plane-api/src/config.py` (S3 OpenSearch consolidation, S5
  validators, S2 BASE_DOMAIN derivation)
- `control-plane-api/src/features/error_snapshots/config.py` (S6 prefix
  rename + alias + conflict scanner + secret masking)
- `control-plane-api/src/opensearch/opensearch_integration.py` (S3 rewire
  to `settings.opensearch_audit`)
- `.env.example` baseline updates (cp-api, cp-ui, gateway, landing-api)
- New tests under `control-plane-api/tests/`:
  - `test_config_base_domain_derivation.py` (7 tests, S2)
  - `test_config_opensearch_consolidation.py` (6 tests, S3)
  - `test_config_validators.py` (7 tests, S5)
  - `test_snapshot_config_alias.py` (11 tests, S6)

PR-A (S1) was a deletion-only commit (`<svc>/k8s/configmap.yaml`); no live
code path to audit. Gateway, portal, and landing-api have no Python source
in this Phase 2 scope.

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| Total findings | **17** |
| By severity | P1=1, P2=7, P3=9 |
| Disposition class | FIX-NOW=16 (Phase 3-A/B/C/D), FOLLOW-UP=1 (INFRA-1c handover), ACCEPTED=0 |
| Pre-existing (not surfaced by rewrite) | 2 (BH-INFRA1a-001, BH-INFRA1a-015) |
| Surfaced by rewrite | 15 |

**Disposition vocabulary** (revision v2):

| Class | Meaning |
|-------|---------|
| **FIX-NOW** | Ship in a Phase 3 micro-PR before the next prod-touching change. Low blast-radius, validator-local fixes. |
| **FOLLOW-UP** | Hand off to a separate ticket / scope. Not blocking; not in the Phase 3 windowed batch. |
| **ACCEPTED** | Documented limitation — no fix planned. Lives in CLAUDE.md. |

**No P0 found.** The audit confirms behavioral preservation for the canonical
prod path (`ENVIRONMENT="production"`, no `BASE_DOMAIN` override, single env
prefix). Bugs cluster in three root-cause families surfaced by the new
validator surfaces.

**Three root-cause families** (per HEG-PAT-020 §5.5 batching):

1. **ENVIRONMENT typo / case bypass** (Family A) — the S5 normalize
   validator only maps the bare lowercase `prod` token to canonical
   `production`. Any other value (case variation `PROD`/`Prod`, typo
   `produciton`, alias `live`) passes through and bypasses all four
   `== "production"` literal checks (auth bypass gate, sensitive-debug
   gate, git provider gate, CORS localhost stripping). 1 bug + 2 reinforcers.
   The S5 PR description was *"validators tightening"*, but the
   downstream gates were never widened to match. **Fail-closed alias map
   is the right fix** (see §2.A).
2. **`_hydrate_opensearch_audit` precedence detection** (Family B) — the
   validator compares `model_dump()` outputs to a fresh default-factory
   instance to detect "explicit sub-model passed". A user passing
   `OpenSearchAuditConfig()` (the default-factory result) explicitly is
   indistinguishable from absence; flat env hydration overrides. 1 bug +
   1 test gap + 1 observability gap. **Fix is `model_fields_set`-based**
   (see §2.B).
3. **SnapshotSettings conflict scanner consistency** (Family C) — the
   scanner does not enumerate field suffixes (spurious conflicts on
   extraneous env vars), does not honor `_env_file=` instantiation
   overrides, the test fixture only clears 6 of 17 field suffixes, AND
   the conflict error message includes raw values gated by a substring
   secret heuristic with known false negatives. **Fix the design root
   cause: never include raw values in conflict errors** — see §2.C; this
   collapses both the heuristic blind-spot and the mutate-on-raise
   side-effect.

**Migration leftover**: PR-E did not migrate `test_snapshot_config.py` and
`test_snapshot_storage_ops.py` to the new prefix (15 hits of
`STOA_SNAPSHOTS_*`, 0 of `STOA_API_SNAPSHOT_*`). The plan §2.6.d explicitly
required migration. Small direct patch in Phase 3-D.

**Severity floor**: nothing in this audit raises a hot prod incident risk on
the canonical config. The P1 (ENVIRONMENT typo / case bypass) is contingent
on an ops mistake (typo, uppercase casing, or a Helm value indirection that
sets the wrong spelling), but the consequence — silent prod-gate bypass for
sensitive debug flags, auth bypass, git provider, and CORS localhost —
warrants a **fail-closed validator** before the next prod config touch.

**Out-of-scope**: this audit does not cover stoa-gateway Rust code, ArgoCD
manifests, or `stoa-infra/charts/`. Plan §A.3 catalogs the deferred items
(BH-1 KEYCLOAK_ADMIN_CLIENT_SECRET freezing → Phase 2 BH; BH-4 chart
`MCP_GATEWAY_URL` hardcode → INFRA-1b; OPENSEARCH_URL rename → 1b/BH).

---

## 2. Findings

### Family A — ENVIRONMENT typo / case bypass (S5)

#### BH-INFRA1a-001 — Any unrecognized `ENVIRONMENT` value bypasses prod gates

- **Category**: 5.3.4 (security boundary) + 5.3.2 (config defaults).
- **Location**: `control-plane-api/src/config.py:273-302` (validator),
  `:596` (CORS gate), `:784` (git gate), `:810` (sensitive-debug gate),
  `:828` (auth-bypass gate).
- **Severity**: **P1**.
- **Symptom**: The S5 `_normalize_environment` validator surgically maps
  the bare lowercase `prod` token to canonical `production`. Per BH-8
  mitigation, all other strings pass through with caller spelling
  preserved (intentional, to avoid silent case-fold of `Staging`/`dev`).
  But the four downstream consumers literal-check `self.ENVIRONMENT ==
  "production"`. So **any** operator value other than the bare
  lowercase `production` (or `prod`, normalized) skips the prod gates:
  - `_gate_sensitive_debug_flags_in_prod` (LOG_DEBUG_AUTH_TOKENS etc.
    refuse boot in prod) — debug flags ENABLED;
  - `_gate_auth_bypass_in_prod` (`STOA_DISABLE_AUTH=true` refuses boot)
    — bypass ALLOWED;
  - `_hydrate_and_validate_git` (missing GITHUB_TOKEN refuses boot in
    prod) — degrades to warning;
  - `cors_origins_list` (strips localhost/.stoa.local) — localhost
    origins KEEP allowing `api.gostoa.dev`.

  Three concrete failure modes:
  1. **Case variation**: `ENVIRONMENT=PROD` or `Prod` (common in Helm
     value indirection, CI promote-to-prod pipelines).
  2. **Typo**: `ENVIRONMENT=produciton` (not flagged by any validator;
     boots silently in non-prod mode).
  3. **Alias not in the validator's vocabulary**: `ENVIRONMENT=live`,
     `ENVIRONMENT=PROD-EU`, `ENVIRONMENT=on-prem-prod` — operator
     intent is prod, code treats it as "not production".

- **Reproduction** (verified for case + typo):
  ```bash
  cd control-plane-api
  for env in PROD Prod produciton live; do
    ENVIRONMENT=$env STOA_DISABLE_AUTH=true GITHUB_TOKEN=fake \
      python3 -c "from src.config import Settings; \
                  s = Settings(); print(f'{s.ENVIRONMENT!r} bypass={s.STOA_DISABLE_AUTH} \
                  cors_localhost={\"localhost\" in str(s.cors_origins_list)}')"
  done
  # All four boot successfully with bypass=True and cors_localhost=True.
  ```

- **Pre-existing or surfaced by rewrite**: **Pre-existing** (the four
  literal-comparison sites have always been case-sensitive and
  typo-fragile). However the S5 work was framed as *"validators
  tightening"* and explicitly aims at `ENVIRONMENT` consistency between
  cp-api and the gateway — that intent makes the partial fix audit-worthy
  even if the exact-match-bypass predates Phase 2. Plan §4 BH-8
  anticipated the case-fold *risk* (silent rewrite of `Staging`) but not
  the dual concern (case + typo *omission*).

- **Proposed disposition**: **FIX-NOW (Phase 3-A)**. Two options for
  Christophe arbitrage:

  **Option A — minimal, case-insensitive only**:
  ```python
  @field_validator("ENVIRONMENT", mode="before")
  @classmethod
  def _normalize_environment(cls, v: object) -> object:
      if isinstance(v, str):
          value = v.strip()
          if value.casefold() in {"prod", "production"}:
              return "production"
          return value
      return v
  ```
  Closes the case bypass (PROD/Prod/PRODUCTION → production). Does NOT
  close the typo bypass (`produciton` still passes through). Smaller
  diff; no behavior change for non-prod values.

  **Option B — fail-closed alias map (RECOMMENDED)**:
  ```python
  _ENVIRONMENT_ALIASES: Final[dict[str, str]] = {
      "dev": "dev",
      "development": "dev",
      "staging": "staging",
      "test": "test",
      "prod": "production",
      "production": "production",
  }

  @field_validator("ENVIRONMENT", mode="before")
  @classmethod
  def _normalize_environment(cls, v: object) -> object:
      if isinstance(v, str):
          key = v.strip().casefold()
          if key in _ENVIRONMENT_ALIASES:
              canonical = _ENVIRONMENT_ALIASES[key]
              if canonical == "production" and key != "production":
                  _logger.info(
                      "ENVIRONMENT normalized: %r → 'production' "
                      "(CAB-2199 / Phase 3-A — case-insensitive accept).", v
                  )
              return canonical
      raise ValueError(
          f"ENVIRONMENT={v!r} is not recognized. Valid values: "
          f"{sorted(set(_ENVIRONMENT_ALIASES.keys()))}."
      )
  ```
  Closes both case and typo bypass. Small behavior change (rejects
  unknown values at boot — is fail-closed). **Recommended** because
  S5's stated intent was validator tightening + `ENVIRONMENT` drives
  security gates; an unknown ENVIRONMENT should never silently mean
  "non-prod".

  **Recommendation**: B. The case for fail-closed is stronger than
  preserving permissive behavior for arbitrary strings, especially
  given S5's framing. The breakage surface is limited to operators with
  unknown spellings — they'll see a clear error message at boot, not a
  silent prod-gate bypass.

- **Blast radius**: any prod environment where Helm values, a CI
  promote-to-prod pipeline, or an ops typo emits a non-canonical
  `ENVIRONMENT`. Probability: low to medium; consequence: high (silent
  bypass of three security gates + CORS widening).

---

#### BH-INFRA1a-006 — `test_environment_other_values_pass_through_no_case_fold` enshrines the bug

- **Category**: 5.3.8 (test gap / false confidence).
- **Location**:
  `control-plane-api/tests/test_config_validators.py:84-98`.
- **Severity**: **P2**.
- **Symptom**: The test asserts `Settings(ENVIRONMENT="PRODUCTION").ENVIRONMENT
  == "PRODUCTION"` and `Settings(ENVIRONMENT="Staging").ENVIRONMENT ==
  "Staging"` — i.e., it locks in the case-preservation behavior. The test
  body even comments: *"PRODUCTION (uppercase) is NOT mapped to
  production — only the bare `prod` token is. PRODUCTION will fail the
  prod-gate elsewhere because `is_production` checks `== "production"`
  literal — but THIS validator does not silently rewrite it."* This
  comment **mis-describes the security consequence**: there is no
  `is_production` helper, and `PROD`/`Prod`/`PRODUCTION` pass the gates
  rather than failing them. The test body claims a failure mode that
  does not exist.
- **Reproduction**: read the test, then run BH-INFRA1a-001 reproducer.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S5** (test
  added in PR-D, `test_config_validators.py`).
- **Proposed disposition**: **FIX-WITH-A (Phase 3-A)** — the test
  rewrite ships in the same PR as the validator change. The PR should:
  1. Delete the existing test (its assertions become invalid under
     either Option A or B).
  2. Add `test_environment_case_insensitive_mapping` covering PROD/Prod/
     PRODUCTION → production, and dev/Development → dev.
  3. Add `test_environment_unknown_value_rejected` covering
     `produciton`, `live`, `on-prem-prod` (Option B only).
  4. Add `test_prod_gate_fires_on_case_variations`: `Settings(ENVIRONMENT="Prod",
     STOA_DISABLE_AUTH=True)` raises ValueError. **This is the regression
     guard the original test never provided.**

---

#### BH-INFRA1a-016 — `.env.example` cp-api comment encourages the case trap

- **Category**: 5.3.2 (config defaults) + 5.3.7 (observability — docs
  signal).
- **Location**: `control-plane-api/.env.example:13`.
- **Severity**: **P3**.
- **Symptom**: The line `# ENVIRONMENT=dev # dev | staging | production
  (or 'prod', normalized to 'production')` invites operators to read
  "or 'prod' is also fine" as case-insensitive. An operator who sets
  `ENVIRONMENT=Prod` (capitalized for visual readability) will silently
  hit BH-INFRA1a-001.
- **Reproduction**: doc inspection.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S4 / PR-D**
  (this comment is new in the Phase 2 baseline).
- **Proposed disposition**: **COVERED-BY-A (Phase 3-A)**. After the
  validator widens (Option A or B), the comment becomes accurate as-is
  for case-insensitive matching. With Option B the comment should also
  list the accepted values:
  `# ENVIRONMENT=dev   # dev | development | staging | test | prod | production (case-insensitive; unknown values fail at boot).`
  No separate ticket — bundle with Phase 3-A.

---

### Family B — `_hydrate_opensearch_audit` precedence detection (S3)

#### BH-INFRA1a-002 — Default-factory `OpenSearchAuditConfig()` passed explicitly is overridden by flat env

- **Category**: 5.3.6 (error handling / fallback) + 5.3.5 (schema).
- **Location**: `control-plane-api/src/config.py:683-712`
  (`_hydrate_opensearch_audit`).
- **Severity**: **P2**.
- **Symptom**: The validator detects an explicit caller-passed sub-model
  by comparing `self.opensearch_audit.model_dump()` to a fresh
  `OpenSearchAuditConfig().model_dump()`. If they differ, the explicit
  instance wins; if they match, flat env vars hydrate the sub-model.
  When a caller passes a default-factory instance explicitly —
  `Settings(opensearch_audit=OpenSearchAuditConfig())` — the dump-equality
  branch treats it as "default" and proceeds to flat env hydration,
  overriding the caller-passed instance. CLAUDE.md note #2 documents the
  precedence rule as "explicit `Settings(opensearch_audit=...)` wins";
  this corner-case violates that contract.
- **Reproduction** (verified):
  ```bash
  cd control-plane-api
  OPENSEARCH_HOST=https://from-env.example.io AUDIT_BUFFER_SIZE=999 \
  GITHUB_TOKEN=fake ENVIRONMENT=dev \
    python3 -c "from src.config import Settings, OpenSearchAuditConfig; \
                s = Settings(opensearch_audit=OpenSearchAuditConfig()); \
                print(s.opensearch_audit.host, s.opensearch_audit.audit_buffer_size)"
  # Expected: https://opensearch.gostoa.dev 100
  # Actual:   https://from-env.example.io 999  ← flat env clobbered explicit
  ```
- **Pre-existing or surfaced by rewrite**: **Surfaced by S3 rewrite**
  (the validator is new in PR-C).
- **Proposed disposition**: **FIX-NOW (Phase 3-C)**. Replace
  dump-equality with `model_fields_set`:
  ```python
  @model_validator(mode="after")
  def _hydrate_opensearch_audit(self) -> "Settings":
      if "opensearch_audit" in self.model_fields_set:
          return self
      self.opensearch_audit = OpenSearchAuditConfig(
          host=self.OPENSEARCH_HOST,
          user=self.OPENSEARCH_USER,
          password=self.OPENSEARCH_PASSWORD,
          verify_certs=self.OPENSEARCH_VERIFY_CERTS,
          ca_certs=self.OPENSEARCH_CA_CERTS,
          timeout=self.OPENSEARCH_TIMEOUT,
          audit_enabled=self.AUDIT_ENABLED,
          audit_buffer_size=self.AUDIT_BUFFER_SIZE,
          audit_flush_interval=self.AUDIT_FLUSH_INTERVAL,
      )
      return self
  ```
  Pydantic v2 tracks fields-set via `model_fields_set`; if the caller
  explicitly passed `opensearch_audit=...` (any value, default-equal or
  not), the field name appears in that set. Robust, idiomatic, no
  dump comparison.
- **Blast radius**: low — corner case, but contract violation
  documented in CLAUDE.md.

---

#### BH-INFRA1a-007 — Test does not exercise default-factory precedence

- **Category**: 5.3.8 (test gap).
- **Location**:
  `control-plane-api/tests/test_config_opensearch_consolidation.py:86-99`
  (`test_explicit_opensearch_audit_submodel_wins_over_flat_env`).
- **Severity**: **P2**.
- **Symptom**: The test passes `OpenSearchAuditConfig(host="https://explicit.io")`
  — a non-default instance whose dump differs from the default factory.
  It does NOT exercise `OpenSearchAuditConfig()` (default-factory
  instance). The bug in BH-INFRA1a-002 has no regression guard.
- **Reproduction**: read the test.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S3 / PR-C** (new
  test).
- **Proposed disposition**: **FIX-WITH-B (Phase 3-C)**. Counter-test
  ships in the same PR:
  ```python
  def test_explicit_default_factory_submodel_wins_over_flat_env(monkeypatch):
      monkeypatch.setenv("OPENSEARCH_HOST", "https://from-env.example.io")
      s = Settings(opensearch_audit=OpenSearchAuditConfig())
      assert s.opensearch_audit.host == "https://opensearch.gostoa.dev"
  ```

---

#### BH-INFRA1a-012 — `_hydrate_opensearch_audit` lacks debug log on path taken

- **Category**: 5.3.7 (observability).
- **Location**: `control-plane-api/src/config.py:683-712`.
- **Severity**: **P3**.
- **Symptom**: The validator either takes the "explicit sub-model"
  short-circuit or hydrates from flat env. Operators debugging "why is
  `opensearch_audit.host` not what I expected?" have no log breadcrumb
  to distinguish the two paths.
- **Reproduction**: any boot — no log for either branch.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S3 / PR-C**.
- **Proposed disposition**: **FIX-WITH-B (Phase 3-C)**. Add a
  `logger.debug` (NOT info — boot detail, not boot-signal) line for each
  path. Trivial; rides along the B-fix PR.

---

### Family C — SnapshotSettings conflict scanner consistency (S6)

> The Family C fix collapses BH-INFRA1a-003 / 004 / 009 / 011 / 014 / 017
> into a single redesign of the conflict scanner. Key design change:
> **never include raw values in conflict errors**. This eliminates the
> need for the `_is_secret_env_key` heuristic at the error-message
> boundary and removes the mutate-on-raise side effect.

#### BH-INFRA1a-003 — Spurious boot-fail on extraneous env vars matching prefix

- **Category**: 5.3.3 (ordering / state machine) + 5.3.6 (error handling).
- **Location**:
  `control-plane-api/src/features/error_snapshots/config.py:245-303`
  (`_detect_conflicts_and_emit_deprecation`).
- **Severity**: **P2**.
- **Symptom**: The scanner iterates ALL env vars matching either
  `STOA_SNAPSHOTS_*` or `STOA_API_SNAPSHOT_*`, regardless of whether the
  suffix corresponds to a real `SnapshotSettings` field. Setting
  `STOA_SNAPSHOTS_FOO_NOT_A_FIELD=x` plus
  `STOA_API_SNAPSHOT_FOO_NOT_A_FIELD=y` raises
  `ValueError("Conflicting config for suffix 'FOO_NOT_A_FIELD'…")` even
  though `FOO_NOT_A_FIELD` is silently ignored by Pydantic
  (`extra="ignore"`).
- **Reproduction** (verified):
  ```bash
  STOA_SNAPSHOTS_FOO_NOT_A_FIELD=old STOA_API_SNAPSHOT_FOO_NOT_A_FIELD=new \
  ENVIRONMENT=dev GITHUB_TOKEN=fake \
    python3 -c "from src.features.error_snapshots.config import SnapshotSettings; \
                SnapshotSettings()"
  # Boot fails: ValueError: Conflicting config for suffix 'FOO_NOT_A_FIELD'
  ```
- **Pre-existing or surfaced by rewrite**: **Surfaced by S6 rewrite**.
- **Proposed disposition**: **FIX-NOW (Phase 3-B)**. Filter the env scan
  to suffixes that correspond to declared fields (introspect
  `SnapshotSettings.model_fields` — for each field, derive the canonical
  `field_name.upper()` plus any `validation_alias.choices` tail).
  Operationally: prevents leftover `STOA_SNAPSHOTS_*` envs from a shared
  K8s namespace from blocking boot for an unrelated suffix.

---

#### BH-INFRA1a-004 — Conflict scanner does not honor `_env_file=` instantiation override

- **Category**: 5.3.3 (ordering / state machine) + 5.3.6 (error handling).
- **Location**:
  `control-plane-api/src/features/error_snapshots/config.py:259`:
  `env_file_path = cls.model_config.get("env_file") or ".env"`.
- **Severity**: **P2**.
- **Symptom**: The scanner reads the *static class-level* `env_file`
  attribute (default `".env"`, resolved relative to cwd). When a caller
  passes `SnapshotSettings(_env_file=...)` to point at a non-default
  dotenv (e.g., container config at `/etc/myapp/snapshots.env`), Pydantic
  honors the override at field resolution but the validator does NOT.
  A conflict between the cwd `.env` (or absence) and the new prefix in
  env will silently miss the dotenv.
- **Reproduction** (verified):
  ```text
  Setup: tmpdir/config/app.env contains STOA_SNAPSHOTS_ENABLED=false
  cwd:   tmpdir/work (no .env)
  env:   STOA_API_SNAPSHOT_ENABLED=true
  Call:  SnapshotSettings(_env_file="tmpdir/config/app.env")
  Expected: ValueError (conflict false vs true)
  Actual:   enabled=True silently — conflict missed
  ```
- **Pre-existing or surfaced by rewrite**: **Surfaced by S6 rewrite**.
- **Proposed disposition**: **FIX-WITH-C (Phase 3-B)**. Plan §2.6.b
  promised that the alias works "from process env, dotenv file, and
  pydantic-settings secrets sources" — fix, don't document. Two paths
  for the implementation:
  - Extract the `_env_file` runtime arg from the init kwargs in the
    scanner (Pydantic-Settings exposes it before validation runs).
  - OR move conflict detection into a wrapper around
    `get_snapshot_settings()` that has access to the resolved instance
    AND its `_env_file` source.

  Either path satisfies the contract; the wrapper approach is cleaner
  but moves the boot-time semantics one call deeper.

---

#### BH-INFRA1a-009 — `test_legacy_alias_from_dotenv_file_is_honored` and `test_conflict_between_new_env_and_old_dotenv_fails` mask BH-INFRA1a-004

- **Category**: 5.3.8 (test gap / false confidence).
- **Location**:
  `control-plane-api/tests/test_snapshot_config_alias.py:121-140`.
- **Severity**: **P2**.
- **Symptom**: Both tests `monkeypatch.chdir(tmp_path)` (via the autouse
  `_isolated_env` fixture) AND pass `_env_file=str(env_file)` where
  `env_file = tmp_path / ".env"`. The `chdir` alone is what causes the
  validator to read the dotenv (because cwd resolves to tmp_path and
  `.env` is the static default). The `_env_file=` arg is ignored by the
  validator (BH-INFRA1a-004) but happens to point at the same file. The
  tests pass coincidentally; they do not validate the documented "the
  conflict scanner reads BOTH process env and dotenv" contract for any
  non-cwd dotenv path.
- **Reproduction**: read the tests; trace which file path the validator
  actually opens.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S6 / PR-E**.
- **Proposed disposition**: **FIX-WITH-C (Phase 3-B)**. After the C-fix:
  1. Add a counter-test where `_env_file` points outside cwd and cwd has
     no `.env` — assert the legacy alias from the non-default file is
     honored AND a conflict between env and that dotenv fails boot.
  2. Drop `monkeypatch.chdir(tmp_path)` from the fixture for tests that
     should validate `_env_file=` resolution; only chdir for tests that
     intentionally exercise the cwd path.

---

#### BH-INFRA1a-011 — Snapshot test fixture clears only 6 of 17 field suffixes

- **Category**: 5.3.3 + 5.3.8 (test gap).
- **Location**:
  `control-plane-api/tests/test_snapshot_config_alias.py:39-54`
  (`_isolated_env` autouse fixture).
- **Severity**: **P3**.
- **Symptom**: The fixture clears 6 specific suffixes (`ENABLED`,
  `RETENTION_DAYS`, `STORAGE_BUCKET`, `STORAGE_SECRET_KEY`,
  `STORAGE_ACCESS_KEY`, `MASKING_EXTRA_HEADERS`) per prefix. The model
  has ~17 fields. If a runner has any other matching suffix in env (e.g.,
  `STOA_SNAPSHOTS_CAPTURE_ON_4XX=true` from a parent shell), the
  conflict scanner sees it. Currently no observed test flake, but the
  fixture is incomplete by construction.
- **Reproduction**: set any extra suffix in CI env; run the test file.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S6 / PR-E**.
- **Proposed disposition**: **FIX-WITH-C (Phase 3-B)**. Free with the
  C-fix scope-defense — `model_fields` introspection naturally feeds
  the fixture's clear-list. Replace the hardcoded suffix list with
  `for field_name in SnapshotSettings.model_fields: ...`.

---

#### BH-INFRA1a-014 — `_is_secret_env_key` heuristic has known false negatives — but the design fix is to never include values

- **Category**: 5.3.4 (security boundary, defence-in-depth scope).
- **Location**:
  `control-plane-api/src/features/error_snapshots/config.py:54-70`,
  `:281-303` (use site).
- **Severity**: **P3**.
- **Symptom**: Substring match on `SECRET`/`KEY`/`TOKEN`/`PASSWORD`
  misses `JWT`, `BEARER`, `CRED`, `SIGN`, `AUTH`, `SALT`, `PRIVATE`,
  `DSN` (a Postgres URL with embedded password matches NONE of the
  tokens). Operators putting secrets in env vars without a matching
  token substring leak the value in the conflict error message.
- **Reproduction**: `STOA_SNAPSHOTS_DB_DSN="postgres://user:pw@host/db"
  STOA_API_SNAPSHOT_DB_DSN="postgres://user:other@host/db"` → boot fail
  with both DSNs visible in the message.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S6** (heuristic
  introduced; conflict-error-includes-values pattern introduced).
- **Proposed disposition**: **FIX-WITH-C (Phase 3-B)** — design fix
  rather than heuristic patch. The conflict error doesn't NEED to
  include raw values; key names plus a "values differ" marker carry
  enough information for ops to debug. Replacement message format:
  ```text
  ValueError: Conflicting config for suffix 'STORAGE_BUCKET':
    sources: ['env:STOA_SNAPSHOTS_STORAGE_BUCKET', 'env:STOA_API_SNAPSHOT_STORAGE_BUCKET']
    status: values differ — remove the legacy key or align both to the same value.
  ```
  This eliminates the heuristic blind-spot entirely. `_is_secret_env_key`
  stays as a defence-in-depth helper (still useful for a hypothetical
  future log/error path that includes values), but the conflict error
  itself becomes value-blind.
- **Note**: this changes the previous WONT-FIX disposition to FIX-WITH-C.
  The argument for WONT-FIX (heuristic is conservative; substring-match
  has known limits) was right about the heuristic — but wrong about the
  design. The right fix is to remove the need for the heuristic, not
  patch its blind spots.

---

#### BH-INFRA1a-017 — Conflict scanner mutates input dict before raising — obsolete after BH-014 fix

- **Category**: 5.3.6 (error handling) + 5.3.4 (defence-in-depth).
- **Location**:
  `control-plane-api/src/features/error_snapshots/config.py:295-298`.
- **Severity**: **P3**.
- **Symptom**: Just before raising, the validator mutates the input
  `values` dict to redact secret-named keys. The mutation covers
  Pydantic's `ValidationError.input_value=` dump (per CLAUDE.md note #3)
  — a defensive measure to prevent the dict surfacing in the exception
  string.
- **Reproduction**: catch the conflict ValueError; inspect dict — values
  of `*KEY*`/`*SECRET*` keys are `<REDACTED>` instead of the originals.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S6 / PR-E**.
- **Proposed disposition**: **FIX-WITH-C (Phase 3-B)**. Once
  BH-INFRA1a-014's fix lands (no raw values in the conflict error
  message), the mutate-on-raise becomes obsolete. The validator stops
  surfacing values in the message; if any caller wraps SnapshotSettings
  and propagates the input dict, they see the original values
  un-mutated. Drop the mutation block. Update CLAUDE.md note #3 to
  reflect the new design (key-only error, no value-redaction
  side effect).

---

### Family D — BASE_DOMAIN empty-string fallback (S2)

#### BH-INFRA1a-005 — `Settings(BASE_DOMAIN="")` produces inconsistent state

- **Category**: 5.3.6 (error handling / fallback) + 5.3.2 (config
  defaults).
- **Location**: `control-plane-api/src/config.py:655` (validator):
  `base_domain = data.get("BASE_DOMAIN") or "gostoa.dev"`.
- **Severity**: **P2**.
- **Symptom**: An explicit empty `BASE_DOMAIN=""` is preserved on the
  field (presence-based `setdefault`), but the derivation lookup uses
  `or "gostoa.dev"` (truthiness-based) and falls back. Result:
  `Settings(BASE_DOMAIN="").BASE_DOMAIN == ""` while
  `KEYCLOAK_URL == "https://auth.gostoa.dev"` and friends. The
  presence-vs-truthiness asymmetry between BASE_DOMAIN handling and
  derived URL handling is unintentional. The S2 plan §2.2.b documents
  empty-string preservation as the new contract — but only for explicit
  *derived* URL overrides; BASE_DOMAIN itself was never analyzed.
- **Reproduction** (verified):
  ```bash
  cd /tmp; PYTHONPATH=/Users/torpedo/hlfh-repos/stoa/control-plane-api \
  ENVIRONMENT=dev GITHUB_TOKEN=fake \
    python3 -c "from src.config import Settings; \
                s = Settings(BASE_DOMAIN=''); \
                print(repr(s.BASE_DOMAIN), s.KEYCLOAK_URL, s.VAULT_ADDR)"
  # Output: '' https://auth.gostoa.dev https://hcvault.gostoa.dev
  ```
- **Pre-existing or surfaced by rewrite**: **Surfaced by S2 rewrite**
  (the `or "gostoa.dev"` fallback is new in the validator).
- **Proposed disposition**: **FIX-NOW (Phase 3-A bundled)**. Reject
  empty BASE_DOMAIN at validation:
  ```python
  @field_validator("BASE_DOMAIN")
  @classmethod
  def _base_domain_must_not_be_empty(cls, v: str) -> str:
      if not v.strip():
          raise ValueError("BASE_DOMAIN must not be empty")
      return v
  ```
  Plus parametric test:
  ```python
  @pytest.mark.parametrize("value", ["", "   ", "\n", "\t"])
  def test_base_domain_empty_rejected(value):
      with pytest.raises(ValueError, match="BASE_DOMAIN must not be empty"):
          Settings(BASE_DOMAIN=value)
  ```
  Bundles into Phase 3-A because it's the same kind of validator
  tightening (small diff, security-adjacent — empty domain produces
  broken-but-routable URLs that could expose internal endpoints in
  weird Helm misrenderings).
- **Blast radius**: low — operators rarely pass empty strings
  intentionally; but a mis-templated Helm values file
  (`baseDomain: ""`) currently silently falls back to `gostoa.dev`
  defaults in non-prod env, masking the misconfiguration.

---

### Family E — Test/doc cleanup (Phase 3-D direct patches)

#### BH-INFRA1a-008 — `test_get_settings_returns_consolidated_submodel` reads boot-time singleton

- **Category**: 5.3.8 (test gap).
- **Location**:
  `control-plane-api/tests/test_config_opensearch_consolidation.py:123-137`.
- **Severity**: **P3** (downgraded from P2 in v1 — this test only
  asserts isinstance, not behavior; the primary regression guards for
  PR-C are the other 5 tests in the file).
- **Symptom**: The test imports `get_settings` from
  `src.opensearch.opensearch_integration`, which returns
  `settings.opensearch_audit` — and `settings = Settings()` is a
  module-level singleton instantiated once at import time. The
  `_isolated_env` fixture clears env vars per test, but the singleton
  was hydrated BEFORE the fixture ran. The `isinstance` check passes
  trivially; the test does not actually verify behavior under the
  fixture's controlled environment.
- **Reproduction**: read the test.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S3 / PR-C** (new
  test).
- **Proposed disposition**: **FIX-NOW (Phase 3-D)**. Small patch:
  replace the import-and-call with a fresh `Settings(...)`
  instantiation + assert the consolidation contract holds with
  controlled env. The legacy import-compat surface (`from
  src.opensearch.opensearch_integration import get_settings`) is the
  documented contract; test should construct a fresh `Settings` and
  call `get_settings()` against that — patch the module-level singleton
  if needed via `monkeypatch.setattr`.
- **Note**: the broader pattern — any consumer that imports `from
  src.config import settings` captures the boot-time singleton — is
  pre-existing and out of scope for INFRA-1a per se. Flagging only
  because PR-C's test was supposed to validate the consolidation under
  controlled config and accidentally tested the singleton's type
  instead.

---

#### BH-INFRA1a-010 — `test_snapshot_config.py` and `test_snapshot_storage_ops.py` not migrated to new prefix

- **Category**: 5.3.8 (test gap / migration leftover).
- **Location**:
  `control-plane-api/tests/test_snapshot_config.py` (6 hits of
  `STOA_SNAPSHOTS_*`),
  `control-plane-api/tests/test_snapshot_storage_ops.py` (9 hits).
  Zero hits of `STOA_API_SNAPSHOT_*` in either file.
- **Severity**: **P2**.
- **Symptom**: Plan §2.6.d and the §1.5 PR-E description explicitly
  required: *"update existing test_snapshot_config.py and
  test_snapshot_storage_ops.py to use the new prefix as default with one
  test_legacy_* regression case per file using the legacy prefix."*
  PR-E's commit body claims "36/36 existing tests still passing… all use
  legacy prefix via AliasChoices alias path" — i.e., the migration was
  not done. Side effects:
  1. Every `pytest` run emits the deprecation log for the legacy prefix
     (test noise).
  2. Every run increments the Prometheus Counter (one-shot guard caps
     it; metric pollution irrelevant for CI).
  3. The new prefix is not exercised by the existing test corpus —
     only the 11 tests in `test_snapshot_config_alias.py`. If the alias
     logic regresses, the bulk of snapshot tests would still pass.
  4. CAB-2203 sunset becomes a larger migration when the alias surface
     is removed.
- **Reproduction**: `grep -c STOA_SNAPSHOTS_ tests/test_snapshot_*.py`
  (15) vs `grep -c STOA_API_SNAPSHOT_ tests/test_snapshot_*.py` (0).
- **Pre-existing or surfaced by rewrite**: **Surfaced by S6 / PR-E
  scope creep** — plan required migration; PR-E shipped without it.
- **Proposed disposition**: **FIX-NOW (Phase 3-D)**. Direct patch, ~30
  minutes:
  - Replace 15 occurrences of `STOA_SNAPSHOTS_*` with
    `STOA_API_SNAPSHOT_*` across both files.
  - Add 1-2 `test_legacy_prefix_still_works` cases per file (one for
    config, one for storage_ops).
  - Verify no test in either file now triggers the deprecation log
    unintentionally (a `caplog.records` filter at fixture level can
    enforce this).

---

#### BH-INFRA1a-015 — `.env.example` cp-api `OPENSEARCH_HOST` value drift / unclear local-vs-default hint

- **Category**: 5.3.2 (config defaults).
- **Location**: `control-plane-api/.env.example:47`:
  `# OPENSEARCH_HOST=https://localhost:9200`
  vs `control-plane-api/src/config.py:238`:
  `OPENSEARCH_HOST: str = Field(default="https://opensearch.gostoa.dev", exclude=True)`.
- **Severity**: **P3**.
- **Symptom**: The .env.example documents `https://localhost:9200` as
  the example value, but the Settings default is the prod-shaped
  `https://opensearch.gostoa.dev`. Plan §4 BH-3 logged this exact drift
  and claimed *"Fixed inline by S4 (within 1a scope)"*. S4 did not fix
  it (the line is unchanged in PR-D's `.env.example` diff).
- **Reproduction**: doc inspection.
- **Pre-existing or surfaced by rewrite**: **Pre-existing** (BH-3 in
  plan §4); S4 *should* have fixed but did not.
- **Proposed disposition**: **FIX-NOW (Phase 3-D)**. Small comment
  rewrite:
  ```env
  # OpenSearch audit endpoint
  # Default in Settings: https://opensearch.gostoa.dev (prod-shaped)
  # Local-dev override example (uncomment + adjust):
  # OPENSEARCH_HOST=https://localhost:9200
  ```
  Bundles with the BH-010 migration commit in Phase 3-D since both are
  small doc/test patches.

---

### Family F — Hygiene (INFRA-1c handover)

#### BH-INFRA1a-013 — `_Pwd` 3-char alias for `SecretStr` is a Gitleaks workaround

- **Category**: 5.3.5 (type / schema drift).
- **Location**: `control-plane-api/src/config.py:90-95`,
  `:248`.
- **Severity**: **P3**.
- **Symptom**: The 3-char `_Pwd = SecretStr` alias is a documented
  workaround for a Gitleaks false-positive (rule `k8s-secret-password`
  regexes `OPENSEARCH_PASSWORD: <8+ alnum>` patterns; the 9-char
  `SecretStr` literal trips it; `_Pwd` is below the 8-char threshold).
  Pydantic introspection tools that walk
  `Settings.model_fields["OPENSEARCH_PASSWORD"].annotation` may surface
  the alias name `_Pwd` instead of `SecretStr` depending on the Python
  version's resolution. The long-term fix
  (Gitleaks `.gitleaks.toml` allowlist for
  `control-plane-api/src/config.py`) is referenced in the code comment
  but not yet tracked.
- **Reproduction**: introspection-only; no runtime impact.
- **Pre-existing or surfaced by rewrite**: **Surfaced by S3 / PR-C**.
- **Proposed disposition**: **FOLLOW-UP (INFRA-1c handover)**. Bundle
  into the INFRA-1c CI hygiene scope. Allowlist
  `control-plane-api/src/config.py` in `.gitleaks.toml`
  `k8s-secret-password` rule, then remove the `_Pwd` alias and restore
  the direct `SecretStr` annotation. Out of Phase 3 scope because the
  Gitleaks rule lives in repo CI config, not cp-api code. Workaround is
  harmless at runtime.

---

## 3. Phase 3 batching

The 17 findings collapse into **4 micro-PRs + 1 INFRA-1c handover** by
root cause (HEG-PAT-020 §5.5 / §5.6). Each Phase 3 PR is small enough
to fit the CLAUDE.md `<300 LOC` rule.

| Batch | Title | Closes findings | Scope | Priority |
|-------|-------|-----------------|-------|----------|
| **Phase 3-A** | Validators fail-closed (ENVIRONMENT + BASE_DOMAIN) | 001, 005, 006, 016 | `config.py` + `test_config_validators.py` + `test_config_base_domain_derivation.py` + `.env.example` comment | Immediate (P1 inside) |
| **Phase 3-B** | Snapshot conflict scanner hardening | 003, 004, 009, 011, 014, 017 | `features/error_snapshots/config.py` + `test_snapshot_config_alias.py` + CLAUDE.md note #3 | High |
| **Phase 3-C** | OpenSearch precedence detection via `model_fields_set` | 002, 007, 012 | `config.py` + `test_config_opensearch_consolidation.py` | Medium |
| **Phase 3-D** | Snapshot test migration + `.env.example` OpenSearch cleanup + singleton-test fix | 008, 010, 015 | `test_snapshot_config.py`, `test_snapshot_storage_ops.py`, `test_config_opensearch_consolidation.py`, `.env.example` | Medium |
| **INFRA-1c handover** | Gitleaks `.gitleaks.toml` allowlist + `_Pwd` removal | 013 | `.gitleaks.toml` + `config.py` revert | Low (separate scope) |

**Sequencing**: 3-A → 3-B → 3-C → 3-D. 3-A first because it carries the
P1; the rest can ship in any order. 3-D depends on no other batch and
can ship in parallel with 3-B/3-C if reviewer bandwidth allows.

**Recommended commit headers** (commitlint-compliant per memory
`gotcha_commitlint_scope_enum_strict.md`):

```
fix(api): fail-closed ENVIRONMENT validator + reject empty BASE_DOMAIN (CAB-2199 Phase 3-A)
fix(api): scope snapshot conflict scanner to declared fields, drop value display (CAB-2199 Phase 3-B)
fix(api): use model_fields_set for opensearch_audit precedence (CAB-2199 Phase 3-C)
test(api)+docs(api): migrate snapshot tests to STOA_API_SNAPSHOT_*, clarify OPENSEARCH_HOST (CAB-2199 Phase 3-D)
```

**Anti-redundancy check** (HEG-PAT-020 §5.6): each family's fix is
independent — no cross-family fix would collaterally close findings in
another family. Within Family A, the Option B fail-closed validator
naturally closes the doc trap (BH-016) without a separate doc edit.
Within Family C, the design fix (no raw values in conflict error)
collapses BH-014 + BH-017 into the scanner redesign without a separate
heuristic patch.

---

## 4. Out-of-scope findings

Findings discovered during the audit that do not belong in INFRA-1a Phase
2 scope (per plan §A.3). Listed for completeness; not analyzed in detail.

| Item | Location | Plan reference |
|------|----------|----------------|
| `KEYCLOAK_ADMIN_CLIENT_SECRET = os.getenv(...)` at class-definition time | `config.py:197-200` | Plan §4 BH-1 (Phase 2 BH, parallel to S2 fix) |
| `OPENSEARCH_URL` vs `opensearch_audit.host` naming collision | `config.py:449` vs `:257` | Plan §4 BH-2 (INFRA-1b or BH) |
| `MCP_GATEWAY_URL` chart hardcode targets retired `mcp-gateway` Service | `stoa-infra/charts/control-plane-api/templates/deployment.yaml` | Plan §4 BH-4 (INFRA-1b) — **out of cp-api scope** |
| `ALGOLIA_SEARCH_API_KEY` 32-char-hex value hardcoded as default | `config.py:430` | Plan §4 BH-5 (Phase 2 BH or client-anonymization sweep) |
| `ARGOCD_PLATFORM_APPS` hardcoded list | `config.py:333` | Plan §4 BH-6 (Phase 2 BH) |
| `LOG_LEVEL: str = "INFO"` (no Literal validator) — typos silently accepted | `config.py:490` | Plan §4 BH-7 (Phase 2 BH) |
| `CORS_ORIGINS` env override REPLACES rather than merges with derived defaults | `config.py:469`, validator `:669-675` | Plan §4 BH-10 (Phase 2 BH) |

These were explicitly deferred in plan §A.3 and §4. The audit confirms they
remain unfixed but does not re-analyze them; the disposition stays as plan §4
documented.

---

## 5. Notes on plan §4 Bug Hunt seed status

The plan §4 listed 10 seed bugs (BH-1 through BH-10). Status after Phase 2:

| Seed | Plan disposition | Phase 2 outcome | Status post-audit |
|------|------------------|------------------|--------------------|
| BH-1 KEYCLOAK_ADMIN load-time freeze | Defer to BH | Unchanged | Defer to Phase 2 BH (parallel ticket) |
| BH-2 OPENSEARCH_URL naming collision | Defer to BH/1b | Unchanged | Defer to INFRA-1b or BH |
| BH-3 .env.example OPENSEARCH_HOST drift | "Fixed inline by S4" | Not fixed | **Re-flagged as BH-INFRA1a-015**, Phase 3-D direct patch |
| BH-4 chart `MCP_GATEWAY_URL` hardcode | Out of 1a; INFRA-1b ticket required | Not in cp-api scope | INFRA-1b, follow-up ticket per plan §7.1 DoD |
| BH-5 ALGOLIA_SEARCH_API_KEY hardcoded | Defer to BH | Unchanged | Defer to Phase 2 BH |
| BH-6 ARGOCD_PLATFORM_APPS hardcoded list | Defer to BH | Unchanged | Defer to Phase 2 BH |
| BH-7 LOG_LEVEL no Literal | Defer to BH | Unchanged | Defer to Phase 2 BH |
| BH-8 ENVIRONMENT case-fold risk | Mitigated by Pattern A surgical normalize | Implemented | **Mitigation incomplete — see BH-INFRA1a-001** (the dual concern: typo + case-bypass on prod gates). Phase 3-A closes. |
| BH-9 BASE_DOMAIN test fixtures rely on frozen-URL bug | Audit before PR-B opens | Verified clean (existing tests use `monkeypatch.setenv` BEFORE module import or do not assert URLs) | Closed |
| BH-10 CORS_ORIGINS replace-not-merge UX | Defer to BH | Unchanged | Defer to Phase 2 BH |

**Newly surfaced by Phase 2 (this audit)**:
- Family A (1 P1 + 2 reinforcers) — BH-8 mitigation incomplete in the dual
  (typo + case bypass).
- Family B (1 P2 + 1 P2 + 1 P3) — `_hydrate_opensearch_audit` precedence
  detection.
- Family C (4 findings + 2 design-collapsed) — conflict scanner consistency
  and value-display redesign.
- Family D (1 P2) — BASE_DOMAIN empty-string fallback.
- Family E (3 findings) — test isolation, migration leftover, S4 doc
  drift carryover.
- Family F (1 P3) — Gitleaks workaround handover.

---

## 6. Methodology notes

- Categories scanned: HEG-PAT-020 §5.3.1 (async/concurrency),
  §5.3.2 (config defaults), §5.3.3 (ordering), §5.3.4 (auth/security),
  §5.3.5 (type drift), §5.3.6 (error handling), §5.3.7 (observability),
  §5.3.8 (test gaps).
- Reproducers verified live via Python invocations on `main` HEAD
  (commit `451516283`).
- The audit avoided fixing anything per HEG-PAT-020 §5 discipline. The
  branch `audit/infra-1a-phase-2-bug-hunt` carries this report only;
  fixes ship in Phase 3 micro-PRs per §3 batching.
- Scope was strictly the 5 PRs A→E. The Phase 2 commits inspected:
  `93b24c0d3` (PR-A / S1), `55cfd93bb` (PR-B / S2),
  `af2803f13` (PR-C / S3), `12b1a3724` (PR-D / S4+S5),
  `5c5ba14f1` (PR-E / S6).

---

## Revision changelog

### v2 — 2026-05-01 (post-review tightening)

Revised after Christophe-style critique (8/10 diagnostic, 6.5/10 v1
disposition). Substantive changes:

1. **Disposition vocabulary** rewritten from `DEFERRED` / `WONT-FIX` /
   `ALREADY-FIXED-by-root-cause` into `FIX-NOW` / `FOLLOW-UP` /
   `ACCEPTED`. The v1 matrix was too passive — it framed Phase 2
   findings as "open tickets and wait", whereas the right next move is
   a short Phase 3 in 4 micro-PRs.

2. **Phase 3 batching** introduced (§3): 3-A (validators fail-closed),
   3-B (snapshot scanner), 3-C (opensearch precedence), 3-D
   (test/doc cleanup) + INFRA-1c handover for Gitleaks. Replaces the v1
   "5–7 tickets" list (which itself mis-counted: 7 not 5).

3. **BH-INFRA1a-001 expanded** — the symptom now covers the broader
   typo case (`produciton`, `live`, `on-prem-prod`), not just case
   variation. **Recommended fix changed to fail-closed alias map**
   (Option B) over the v1 case-insensitive widening (Option A); both
   options remain documented.

4. **BH-INFRA1a-014 re-classified** from `WONT-FIX` to `FIX-WITH-C`.
   The right design is to never include raw values in the conflict
   error; this collapses the heuristic blind-spot entirely instead of
   patching it. `_is_secret_env_key` stays as defence-in-depth for any
   future log path that includes values.

5. **BH-INFRA1a-017 re-classified** from `WONT-FIX` to `FIX-WITH-C`.
   Once BH-014's design fix lands, the mutate-on-raise becomes
   obsolete; drop it.

6. **BH-INFRA1a-008 demoted** from P2 to P3. The test only asserts
   isinstance — it's not the primary regression guard for PR-C (the
   other 5 tests in the file are).

7. **BH-INFRA1a-016 disposition** changed from
   `ALREADY-FIXED-by-root-cause` to `COVERED-BY-A` — the root cause is
   not yet fixed, so claiming "ALREADY-FIXED" was inaccurate.

8. **Severity totals adjusted**: P1=1, P2=7 (was 8), P3=9 (was 8). One
   demotion; total still 17.

9. **Out-of-scope §4** and **plan-seed §5** sections kept verbatim
   from v1 — accurate as-is.

### v1 — 2026-05-01 (initial audit)

Initial 17-finding audit per HEG-PAT-020 §5 discipline. Disposition
matrix used `DEFERRED` / `WONT-FIX` / `ALREADY-FIXED-by-root-cause`
classes. Replaced in v2.

---

**End of Bug Hunt report.** Christophe arbitrates the Phase 3-A Option
A vs Option B. Phase 3-A is unblocked once that arbitrage lands; 3-B/C/D
are unblocked immediately.
