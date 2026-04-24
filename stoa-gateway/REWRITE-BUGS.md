# REWRITE-BUGS — GW-2 config rewrite delta

> This file closes the documentation debt from `REWRITE-PLAN.md §7.4, §10, §11`
> which promised a retrospective on bugs found while splitting `src/config.rs`
> into a facade + 9 sub-modules. The full audit lives in
> [`BUG-REPORT-GW-2.md`](./BUG-REPORT-GW-2.md) (13 findings, all pre-dating the
> rewrite).

## TL;DR

The rewrite itself introduced **no regressions**: defaults are snapshotted
byte-for-byte via `insta::assert_json_snapshot!(Config::default())`, the public
API (`pub use …`) is intact, and all 30 internal callers + 8 test callers
compile unchanged.

The audit surfaced **10 pre-existing bugs** that the rewrite made visible.
They are all fixed in the `fix/gw-2-bug-hunt-batch` commit, with the following
caveats (deferred):

- **k8s manifest migration** — the prod Deployment in
  `stoa-gateway/k8s/deployment.yaml` exposes ~50 nested env vars with a single
  underscore (e.g. `STOA_API_PROXY_ENABLED`) that were silently ignored
  before the rewrite. The loader is now fixed (`Env::prefixed("STOA_").split("__")`),
  so **the single-underscore form remains no-op** (backward compatible). The
  manifest is **not migrated** in this commit because flipping to the
  double-underscore form would turn on the API Proxy feature in prod for the
  first time — a behavioural change that needs Council review, not a bug fix.
- **DpopConfig** lives in `src/auth/dpop.rs`, outside `src/config/`. Its
  nested env vars (`STOA_DPOP__*`) are covered by the loader split, but its
  doc-comments still advertise single-underscore. Doc drift tracked in
  ticket **GW-3**.
- **External docs** in `stoa-signed-commits-policy/docs/CAB-864-MTLS-DESIGN.md`
  (separate repo) document single-underscore env vars. Out of scope here,
  needs a cross-repo PR.

## Fix map

| Finding | Fix | Tests |
|---|---|---|
| P0-1 — env vars ignored for nested structs | `Env::prefixed("STOA_").split("__")` in `src/config/loader.rs`. All doc-comments in `src/config/*.rs` migrated to `STOA_MTLS__ENABLED` etc. | 3 integration tests in `tests/config_regression_guards.rs` |
| P0-2 — CSV startup crash on `Vec<String>` | Custom `string_list` deserializer in `src/config/deserializers.rs`, applied to `snapshot_extra_pii_patterns` + `mtls.trusted_proxies` + `mtls.allowed_issuers` + `mtls.required_routes`. | 9 unit tests + 3 integration tests |
| P0-3 — missing `REWRITE-BUGS.md` | This file. Cross-references `BUG-REPORT-GW-2.md`. | N/A (doc only) |
| P1-4 — `Config::default()` vs `#[serde(default)]` drift | 4 fields converted from `#[serde(default)]` to `#[serde(default = "fn")]` returning `Some(…)`. | 1 integration test |
| P1-5 — secrets leakable via `Debug` | Custom `impl Debug for Config` in `src/config.rs` that redacts 10 secret fields. `Redacted<T>` wrapper for `FederationUpstreamConfig.auth_token` (`#[serde(transparent)]` so the JSON shape is preserved). | 2 integration tests + 6 unit tests on `Redacted` |
| P1-6 — `validate()` returned nothing | Now `-> Result<(), ConfigError>` with 5 invariants (port, mtls+trusted_proxies, federation+upstreams, sender_constraint+backing, tcp_rate_limit finite). `main.rs` propagates via `?`. | 11 unit tests covering each invariant + defaults |
| P1-7 — snapshot does not cover round-trip | New `tests/fixtures/config_minimal.yaml` + `config_production.yaml` parsed and validated in `tests/config_regression_guards.rs`. JSON round-trip test. | 3 integration tests |
| P2-8 — `default_true` duplicated | `ProxyBackendConfig.circuit_breaker_enabled` now references `crate::config::defaults::default_true` (single source). | Covered by existing `test_proxy_backend_defaults` |
| P2-10 — `tcp_rate_limit_per_ip` accepts NaN/∞ | Absorbed into P1-6 (`TcpRateLimitNotFinite` variant). | 2 unit tests (inf + NaN) |
| P2-12 — `ExpansionMode` alias has no deadline | `TODO(GW-3)` comment added in `src/config/expansion.rs`. | N/A (tracked) |

## Deferred

- **P2-9** — string → enum migration for 7 soft-typed fields (`git_provider`,
  `log_level`, `log_format`, `environment`, `shadow_capture_source`,
  `supervision_default_tier`, `llm_proxy_provider`). Moved to Linear ticket
  **GW-3: Type config strings to enums** (estimated ~7 micro-PRs).
- **P2-11** — allow-list for `policy_path` / `ip_blocklist_file` /
  `prompt_cache_watch_dir`. Defense-in-depth, low priority, moved to GW-3.
- **P3-13, P3-14** — doc-comment inconsistency on `detailed_tracing` and
  `default_fn` repetition. Pure cosmetic, left in backlog.

## Known migration gaps (not fixed in this commit)

| Location | Symptom | Action |
|---|---|---|
| `stoa-gateway/k8s/deployment.yaml` | ~50 single-underscore env vars for `api_proxy.*`. Currently no-op (historical). | Migrate to double-underscore **only after Council reviews the behavioural change** (activates API Proxy in prod). |
| `stoa-signed-commits-policy/docs/CAB-864-MTLS-DESIGN.md` | 15+ single-underscore `STOA_MTLS_*` entries in a design doc. | Cross-repo PR. |
| `src/auth/dpop.rs` (`DpopConfig` doc-comments) | Advertise `STOA_DPOP_ENABLED` single-underscore. | Follow-up inside GW-3 or a dedicated micro-PR. |

## Verification

Run locally (or in CI):

```bash
cd stoa-gateway
cargo check
RUSTFLAGS='-Dwarnings' cargo clippy --all-targets -- -D warnings
cargo fmt --check
cargo test --test config_regression_guards   # 12 targeted guards
cargo test                                    # full suite (no regressions)
```

Smoke check that the env var split is live:

```bash
# Single-underscore stays no-op (backward compat):
STOA_MTLS_ENABLED=true cargo run -- --help
# → config.mtls.enabled == false

# Double-underscore takes effect:
STOA_MTLS__ENABLED=true STOA_MTLS__TRUSTED_PROXIES="10.0.0.0/8" cargo run
# → Config::load() succeeds, config.mtls.enabled == true
```
