# FIX-PLAN — CAB-2165 GW-3 Gateway config cleanup

**Branch target**: `fix/cab-2165-gw-3-cleanup` (to be cut from `main` after current GW-2 PR #2523 merge — currently `80017fb9d`).
**Current working branch**: `fix/cab-2164-ui-3-cleanup` — Phase 1 only, no code yet.
**Scope**: 3 bundles absorbed from GW-2 deferrals — P2-9 (String→enum), P2-11 (path allow-list), plus DpopConfig doc completion from P0-1 GW-2.
**Estimate**: ~450 LOC across Bundle 1 (largest), ~40 LOC Bundle 2, ~15 LOC Bundle 3.

---

## A. Bundle 1 — String → enum (7 fields)

### A.1 Evidence gathered

| Field | Line | Defaults | Consumers (real) | Chart/env usage |
|-------|------|----------|------------------|-----------------|
| `git_provider: String` | `config.rs:142` | `"gitlab"` | `lib.rs:362`, `handlers/admin/health.rs:40`, `git/mod.rs:62` (match on "github" else GitLab) | No chart value; `STOA_GIT_PROVIDER` env only |
| `log_level: Option<String>` | `config.rs:188` | `Some("info")` | **0 real** (tracing uses `RUST_LOG` via `EnvFilter` at `main.rs:224`) | `charts/…-deployment.yaml:65`, `k8s/deployment.yaml:49`, docker-compose multiple |
| `log_format: Option<String>` | `config.rs:191` | `Some("json")` | **0 real** | `charts/…-deployment.yaml:67`, `k8s/deployment.yaml:51` |
| `environment: String` | `config.rs:266` | `"dev"` | `control_plane/registration.rs:170` (clone into registration payload) | `charts/values.yaml:123,211,409,530`, docker-compose multiple |
| `shadow_capture_source: Option<String>` | `config.rs:250` | `None` | **0 real** | Not in any chart/env — doc-only field |
| `supervision_default_tier: String` | `config.rs:655` | `"autopilot"` | `supervision/mod.rs:128` (`from_config_default` takes `&str`, internally maps to `SupervisionTier` enum — already has "co-pilot" alias) | Not in chart defaults |
| `llm_proxy_provider: Option<String>` | `config.rs:687` | `None` | **0 real** | Not in chart defaults |

**Pattern to follow** — `config/expansion.rs` (`ExpansionMode`): enum with `#[serde(rename_all = "kebab-case")]` + `#[serde(alias = "snake_form")]` for backward compat.

### A.2 YAML fixtures and production values

Grep across `charts/`, `deploy/`, `stoa-gateway/tests/fixtures/`, `k8s/`:
- `log_level`: `"info"`, `"debug"`, `{{ .Values… | default "info" }}` → all lowercase canonical values.
- `log_format`: `"json"` only.
- `environment`: `"dev"`, `"staging"`, `"prod"` — **all lowercase canonical**.
- `git_provider`: no values set in chart/env fixtures — only the default `"gitlab"` via `default_git_provider`.
- `supervision_default_tier`: no values set in chart/env fixtures — only default `"autopilot"`.
- `shadow_capture_source`: no values set in chart/env fixtures.
- `llm_proxy_provider`: no values set in chart/env fixtures.

**Conclusion**: no deployed YAML/env uses non-canonical casing. Strict enums won't break any known config.

### A.3 Proposed enum shapes

All enums use `#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]` + `#[serde(rename_all = "snake_case")]` by default (kebab for `shadow_capture_source` since the documented values include a hyphen).

```rust
// src/config/enums.rs (new file; re-exports from `config` façade)

/// Git provider for UAC sync. Env: STOA_GIT_PROVIDER (canonical: "gitlab" | "github").
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum GitProvider {
    #[default]
    Gitlab,
    Github,
}

/// Tracing verbosity level (informational — tracing itself is driven by RUST_LOG).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum LogLevel {
    Trace,
    Debug,
    #[default]
    Info,
    Warn,
    Error,
}

/// Log output format (informational — formatter wiring lives in main.rs).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum LogFormat {
    #[default]
    Json,
    Pretty,
    Compact,
}

/// Deployment environment label for registration + observability.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum Environment {
    #[default]
    Dev,
    Staging,
    Prod,
}

/// Shadow mode traffic capture source (ADR-024 §5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ShadowCaptureSource {
    Inline,
    EnvoyTap,
    PortMirror,
    Kafka,
}

/// Default supervision tier when X-Hegemon-Supervision header is absent (CAB-1636).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum SupervisionDefaultTier {
    #[default]
    Autopilot,
    // Back-compat: `SupervisionTier::from_header` at supervision/mod.rs:52 accepts
    // both "copilot" and "co-pilot" today. Keep parity by aliasing.
    #[serde(alias = "co-pilot")]
    Copilot,
    Command,
}

/// LLM proxy provider format (CAB-1568).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LlmProxyProvider {
    Anthropic,
    Mistral,
    Openai,
}
```

### A.4 Consumer migration

- `git/mod.rs:62` `match config.git_provider.as_str()` → `match config.git_provider`.
- `lib.rs:362` similar — pattern-match on enum.
- `handlers/admin/health.rs:40` — field currently `git_provider: String`; the health payload is serialized JSON, so changing the source type to `GitProvider` either:
  - preserves the wire-format via `Serialize` on the enum (snake_case JSON — same string as today); **or**
  - we add a `.to_string_canonical()` helper. Reco: rely on the enum's `Serialize` impl, no wrapper.
- `control_plane/registration.rs:170` payload `environment: String` — registration struct lives locally, change its field to `Environment` enum or call `config.environment.to_string()`. Reco: change registration payload type too for cleanliness.
- `supervision/mod.rs:128` `from_config_default(&self.config.supervision_default_tier)` takes `&str` — refactor to take `SupervisionDefaultTier` and map 1:1 to `SupervisionTier`. No behavior change.

### A.5 Regression guards (Bundle 1)

Add under `src/config/tests.rs`:

1. `test_git_provider_rejects_unknown_value` — `git_provider: "bitbucket"` YAML parse → `Err` with "unknown variant" in message. **Replaces** existing `test_git_provider_unknown_value_treated_as_gitlab` (line 200) which locks in the silent-fallback anti-pattern.
2. `test_git_provider_default_is_gitlab` — `Config::default().git_provider == GitProvider::Gitlab`.
3. `test_environment_accepts_dev_staging_prod` — all three parse.
4. `test_environment_rejects_unknown_value` — "mordor" → `Err`.
5. `test_log_level_all_standard_values` — trace/debug/info/warn/error all parse.
6. `test_log_format_rejects_unknown` — "xml" → `Err`.
7. `test_shadow_capture_source_kebab` — "envoy-tap" → `EnvoyTap`.
8. `test_supervision_tier_copilot_alias` — "co-pilot" + "copilot" both → `Copilot` (parity with `SupervisionTier::from_header`).
9. `test_llm_proxy_provider_all_variants` — anthropic/mistral/openai all parse.

### A.6 Insta snapshot drift

`snapshot_default_config.snap` lines 39/40/51/54/158/164 currently serialize string values ("info"/"json"/"dev"/"autopilot"/null). Since `#[serde(rename_all = "snake_case")]` + `Default` on enums produces the same JSON strings, **the snapshot should NOT drift** for fields that previously defaulted to a canonical string. Verification step in Phase 3: `cargo test snapshot_default_config` must pass without review. If diff appears, something is off — investigate rather than accept.

**Edge case**: `shadow_capture_source` and `llm_proxy_provider` default to `None` → snapshot stays `null`. No drift.

---

## B. Bundle 2 — Path warning (P2-11)

### B.1 Evidence

| Field | Line | Consumed by | Usage |
|-------|------|-------------|-------|
| `policy_path: Option<String>` | `config.rs:179` | `state.rs:172`, `policy/opa.rs:120/240` | Rego policy file load |
| `ip_blocklist_file: Option<String>` | `config.rs:801` | `tcp_filter.rs:53` | IP/CIDR list read at startup |
| `prompt_cache_watch_dir: Option<String>` | `config.rs:593` | `state.rs:680` | Directory watcher (notify) |

### B.2 Decision D.2 — Option C (warn-only) recommended

Rationale from BUG-REPORT GW-2 P2-11: operator configuring the pod already has FS access. Defense-in-depth only.

- **Option A** (hard allow-list via `STOA_CONFIG_ALLOWED_PATHS`) — would break any existing deployment with `policy_path: /tmp/...` or custom mount paths. Not shipped for CAB-2165 today.
- **Option C** (warn-only) — logs a `tracing::warn!` at startup for any path not under `/etc/stoa/` or `/var/stoa/` or relative-path-in-cwd. Visible in structured logs; doesn't break anything. **Chosen.**

### B.3 Shape

New module `src/config/path_safety.rs`:

```rust
//! Defense-in-depth path validation for filesystem-backed Config fields.
//! Logs a warning when a configured path sits outside canonical STOA prefixes.
//! Does NOT reject — operator retains full control (see CAB-2165 Bundle 2 / P2-11 GW-2).

use std::path::Path;
use tracing::warn;

/// Paths under any of these prefixes are considered "safe" (no warning).
const SAFE_PREFIXES: &[&str] = &["/etc/stoa/", "/var/stoa/", "/opt/stoa/"];

/// Emit a warning if `path` is outside the safe prefix set.
/// Relative paths are always allowed (treated as explicit operator intent within cwd).
pub(crate) fn warn_if_unsafe(field: &str, path: &str) {
    let p = Path::new(path);
    if p.is_relative() {
        return;
    }
    let canonical_ok = SAFE_PREFIXES.iter().any(|prefix| path.starts_with(prefix));
    if !canonical_ok {
        warn!(
            field = field,
            path = path,
            "config path outside canonical /etc/stoa/ — defense-in-depth warning (CAB-2165)"
        );
    }
}
```

Wire the check from `Config::validate()` (or equivalent startup hook — verify existing shape) for each of the 3 fields. No functional change; log only.

### B.4 Regression guards (Bundle 2)

Under `src/config/path_safety.rs` `#[cfg(test)] mod tests`:
1. `test_safe_prefix_no_warn` — `/etc/stoa/policies/default.rego` → no-op (use `tracing_test` or probe log capture).
2. `test_unsafe_prefix_emits_warn` — `/tmp/custom.rego` → 1 warn event captured.
3. `test_relative_path_no_warn` — `policies/default.rego` → no-op.

If `tracing_test` isn't already a dev-dep, we fall back to a direct unit check: `warn_if_unsafe` returns `bool` (or `Option<&'static str>` describing the reason) and we assert the predicate — logging stays a side effect.

---

## C. Bundle 3 — DpopConfig doc completion (P0-1 GW-2 completion)

### C.1 Evidence

- Sister structs — `MtlsConfig` (src/config/mtls.rs:12–70), `SenderConstraintConfig` (16/21/26), `LlmRouterConfig` (11/16/21), `ApiProxyConfig` (13/19/24) — **all have per-field `/// Env: STOA_X__Y` doc comments** post-GW-2 P0-1 (double underscore).
- `DpopConfig` lives in `src/auth/dpop.rs:39–66` — outside `src/config/` — **has ZERO per-field env-var doc comments**.
- Top-level `config.rs:360–362` mentions `STOA_DPOP__ENABLED`/`STOA_DPOP__REQUIRED` but the nested struct itself does not document any.
- `grep -rnE "STOA_DPOP_[A-Z]" src/ | grep -v "__"` → 0 hits for single-underscore. Clean, just the per-field docs are absent.

### C.2 Fix

Add a module-level doc header on `DpopConfig` and per-field `/// Env: STOA_DPOP__<FIELD>` comments on all 6 fields, mirroring the MtlsConfig pattern. No logic change.

Fields to document:
- `enabled` → `STOA_DPOP__ENABLED`
- `required` → `STOA_DPOP__REQUIRED`
- `max_age_secs` → `STOA_DPOP__MAX_AGE_SECS`
- `clock_skew_secs` → `STOA_DPOP__CLOCK_SKEW_SECS`
- `jti_cache_ttl_secs` → `STOA_DPOP__JTI_CACHE_TTL_SECS`
- `jti_cache_max` → `STOA_DPOP__JTI_CACHE_MAX`

### C.3 No test needed

Pure doc change.

---

## D. Arbitrages to resolve

### D.1 — Bundle 1 fallback strategy per field

**Recommendation: strict enum across the board, no legacy aliases except `co-pilot` for `SupervisionDefaultTier`.**

Rationale:
- No deployed YAML/env uses non-canonical casing (A.2 grep).
- Silent fallthrough is a known foot-gun (P2-9 called it out).
- `SupervisionTier::from_header` at `supervision/mod.rs:52` already accepts "co-pilot" as a hyphenated form — preserving the alias avoids a user-visible break for anyone who copy-pasted from an HTTP header example.

**Field-by-field:**
| Field | Strategy | Alias |
|-------|----------|-------|
| `git_provider` | Strict | none |
| `log_level` | Strict | none |
| `log_format` | Strict | none |
| `environment` | Strict | none |
| `shadow_capture_source` | Strict | none |
| `supervision_default_tier` | Strict | `co-pilot → Copilot` |
| `llm_proxy_provider` | Strict | none |

### D.2 — Bundle 2 scope

**Option C (warn-only). ~30 LOC for module + wiring + 3 tests.** Confirmed in B.2.

### D.3 — Bundle 3 scope

**Grep confirms**: per-field doc comments missing on all 6 `DpopConfig` fields. Bundle 3 IS in scope — not `ALREADY-FIXED`. ~15 LOC of doc comments.

---

## E. Commit strategy

Execute in ascending-risk order. Commits are numbered in execution order (1 → 3):

### Commit 1 (smallest) — `docs(gateway/config)`
```
docs(gateway/config): complete DpopConfig env-var doc alignment

GW-2 P0-1 migrated 30+ doc-comments to the STOA_*__* (double underscore)
pattern for MtlsConfig, SenderConstraintConfig, LlmRouterConfig, and
ApiProxyConfig. DpopConfig (src/auth/dpop.rs, not src/config/) was
outside that pass — its 6 fields had zero env-var documentation.

This completes the alignment with per-field `/// Env: STOA_DPOP__<FIELD>`
comments mirroring the MtlsConfig pattern.

No behavior change.

Refs: CAB-2165 Bundle 3 / P0-1 GW-2 completion
```

### Commit 2 (isolated) — `feat(gateway/config)`
```
feat(gateway/config): defense-in-depth warning on filesystem paths

New `src/config/path_safety.rs` module + startup-time check on
policy_path, ip_blocklist_file, and prompt_cache_watch_dir. Emits a
tracing::warn! when any of these point outside /etc/stoa/, /var/stoa/,
or /opt/stoa/ (absolute paths only; relative paths are trusted as
explicit operator intent within cwd).

Does NOT reject or fail startup. Purely observability.

Regression guards: 3 new tests under path_safety::tests.

Closes: P2-11 GW-2 / CAB-2165 Bundle 2
```

### Commit 3 (largest) — `refactor(gateway/config)`
```
refactor(gateway/config): type 7 soft String fields as enums

Fields migrated (strict parsing, no silent fallthrough):
- git_provider: GitProvider { Gitlab, Github }
- log_level: LogLevel { Trace, Debug, Info, Warn, Error }
- log_format: LogFormat { Json, Pretty, Compact }
- environment: Environment { Dev, Staging, Prod }
- shadow_capture_source: ShadowCaptureSource (kebab-case; Inline,
  EnvoyTap, PortMirror, Kafka)
- supervision_default_tier: SupervisionDefaultTier (alias `co-pilot`
  for parity with SupervisionTier::from_header)
- llm_proxy_provider: LlmProxyProvider { Anthropic, Mistral, Openai }

Consumer sites updated: git/mod.rs, lib.rs, handlers/admin/health.rs,
control_plane/registration.rs, supervision/mod.rs.

Breaking semantic: unknown values (e.g. git_provider: "bitbucket")
now fail `Config::load()` with a clear "unknown variant" error
instead of silently falling through to a default. Prod YAML grep
confirms no deployed config uses non-canonical casing.

Regression guards: 9 new tests replacing the legacy
test_git_provider_unknown_value_treated_as_gitlab which encoded the
silent-fallthrough anti-pattern.

Closes: P2-9 GW-2 / CAB-2165 Bundle 1
```

---

## F. Risks identified

1. **Bundle 1 insta snapshot drift** — `Config::default()` serializes each new enum's default variant. Expected: same JSON strings as today (`"info"`, `"json"`, `"dev"`, `"autopilot"`, `null` for the `Option`s). If diff surfaces, Option-to-Option wrapping may be off and needs `#[serde(default)]` on the inner type rather than `#[serde(default = "…")]` helper. Verification step F.ext: run `cargo test snapshot_default_config` before clicking-through any `cargo insta review`.
2. **Bundle 1 consumer API mismatch** — `handlers/admin/health.rs:40` serializes `git_provider` into a payload already shipped to CP API. Mitigation: snake_case serialization preserves wire format 1:1 — `GitProvider::Gitlab` → `"gitlab"`. Registration payload at `control_plane/registration.rs:170` similar. Verify via `cargo test --package stoa-gateway --test '*'` (contract tests if any) and CI green.
3. **Bundle 1 dormant fields' footprint** — 4 of 7 fields (`log_level`, `log_format`, `llm_proxy_provider`, `shadow_capture_source`) have ZERO real consumers in-tree. Migration is risk-free on those, but one may wonder whether to delete them outright. **Out of scope for CAB-2165** — pure dead-code removal is a separate cleanup.
4. **Bundle 2 wiring point** — `Config::validate()` may not exist yet; if so, call sites: `Config::load()` return path in `loader.rs` or `main_wiring.rs` startup. Phase 2 must locate the single startup-time validation hook and thread warnings there, not scatter them.
5. **Bundle 3 is near-zero risk** — 6 lines of doc comment insertion.
6. **CI clippy/fmt** — all 3 commits must pass `cargo clippy --all-targets -- -D warnings` + `cargo fmt --check`. Zero `#[allow(...)]` without justification (repo rule).

---

## G. Phase 2 execution plan

After plan approval (commits numbered in execution order):

1. Rebranch from fresh `main`: `git checkout main && git pull && git checkout -b fix/cab-2165-gw-3-cleanup`.
2. **Commit 1** (docs, trivial) — add 6 doc-comment lines + module-level `//! Env-var prefix` header on `DpopConfig`.
3. **Commit 2** (path warn) — create `src/config/path_safety.rs`, register it in `src/config.rs` mod list, wire `warn_if_unsafe` into startup, add 3 tests on the `bool` predicate (no tracing capture).
4. **Commit 3** (enum migration) — add `src/config/enums.rs`, update 7 fields + defaults + 5 consumer sites, swap 1 legacy test for 9+ new strict-parse tests, run insta snapshot check.
5. Run full validation suite (see H).
6. Push + open PR `fix(gateway): close CAB-2165 GW-3 cleanup — 3 bundles` with per-commit bullet list in description.

**STOP after Phase 2** for review before Phase 3 validation commands.

### G.1 Adjustments from review (2026-04-24)

1. **Commit numbering**: commits now numbered 1→3 in execution order (was 3→2→1). Less confusing in logs/PR.
2. **Defaults typed end-to-end**: helpers migrate with the fields — no lingering `Some("info".to_string())` in `defaults.rs`. New shapes:
   ```rust
   fn default_log_level() -> Option<LogLevel> { Some(LogLevel::Info) }
   fn default_log_format() -> Option<LogFormat> { Some(LogFormat::Json) }
   fn default_environment() -> Environment { Environment::Dev }
   fn default_git_provider() -> GitProvider { GitProvider::Gitlab }
   fn default_supervision_tier() -> SupervisionDefaultTier { SupervisionDefaultTier::Autopilot }
   ```
3. **`Display` / `as_str` on enums consumed as string**: `GitProvider`, `Environment`, `SupervisionDefaultTier` get either `impl Display` or `fn as_str(self) -> &'static str`. For `control_plane/registration.rs:170`, explicit `config.environment.to_string()` at the payload boundary — keep the payload struct's `environment: String` field unchanged to avoid touching the wire contract.
4. **`SupervisionDefaultTier` alias**: canonical `copilot` via `#[serde(rename_all = "snake_case")]` + `#[serde(alias = "co-pilot")]`. Test both values.
5. **No implicit aliases**: strict parsing per D.1 — no `GitHub`/`GITHUB`/`production` tolerant forms. Only the explicit `co-pilot` alias survives.
6. **Path safety uses `Path::starts_with`**: component-aware, avoids `/etc/stoa-malicious` false negative:
   ```rust
   let safe_prefixes = [Path::new("/etc/stoa"), Path::new("/var/stoa"), Path::new("/opt/stoa")];
   let safe = safe_prefixes.iter().any(|prefix| p.starts_with(prefix));
   ```
7. **Testable predicate for path safety**:
   ```rust
   pub(crate) fn is_path_outside_safe_prefixes(path: &str) -> bool { … }
   pub(crate) fn warn_if_unsafe(field: &str, path: &str) {
       if is_path_outside_safe_prefixes(path) { warn!(field, path, "…"); }
   }
   ```
   Tests assert on the predicate — no `tracing_test` dev-dep, no capture fragility.
8. **Env-var deserialization tests (Bundle 1)**: add at least `STOA_GIT_PROVIDER=github` and `STOA_ENVIRONMENT=prod` via Figment (`tests/fixtures` or inline `Jail::expect_with`). Verifies enums parse from env, not just YAML.
9. **Snapshot drift = investigate, never auto-accept**: if `snapshot_default_config.snap` diffs, stop and trace back to a defaults helper or a `rename_all` mismatch. No `cargo insta accept` by reflex.

---

## H. Phase 3 validation gate

```bash
cargo check                                                # 0 warnings
cargo clippy --all-targets -- -D warnings                  # 0 issues
cargo fmt --check                                          # clean
cargo test --package stoa-gateway                          # all pass
cargo test --package stoa-gateway snapshot_default_config  # no drift (or justified review)
```

Smoke:
- Load `tests/fixtures/config_production.yaml` → parse OK (no enum rejection).
- Load synthetic `environment: "mordor"` YAML → `Err` with "unknown variant" in message.
- Startup with `policy_path: /tmp/custom.rego` → 1 warn log line "config path outside canonical…".
- Linear CAB-2165 → Done + commit SHAs linked.
- `BUG-REPORT-GW-2.md` → mark P2-9 and P2-11 as `FIXED` (currently `DEFERRED → GW-3`).

**STOP after Phase 3.** Validation evidence + SHA list → Linear comment.

---

## I. Out of scope (deliberately deferred)

- Deleting dead-code fields `log_level`, `log_format`, `llm_proxy_provider`, `shadow_capture_source` (0 consumers) — separate cleanup ticket if desired.
- Path Option A (hard allow-list via `STOA_CONFIG_ALLOWED_PATHS`) — revisit if Option C warnings accumulate in prod.
- P3-13 / P3-14 (`detailed_tracing` doc vs code, `default_*` helper consolidation) — `BACKLOG` per GW-2, not claimed here.
