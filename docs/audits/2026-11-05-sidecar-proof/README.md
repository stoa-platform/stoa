# Local sidecar router proof

Date: 2026-11-05. Platform: macOS, Darwin arm64. Rust: 1.99.1.
Base/runtime source: `99d71433e7cd3c1d72ce066d97cfd67562ce3dc0`.
The only Rust change is test code in `src/lib.rs`; production code is unchanged.
Test source blob: `7a2cd9404e2b19c3a0f39e5e7d87a57efa4e79e1`.
Measurements used this base SHA plus that test-only change, before the evidence
commit. The containing commit preserves both the tests and this record.

## Scope

The tests call the production `build_router` in sidecar mode via
`tower::ServiceExt::oneshot`, including HTTP JSON extraction, the shared decision
engine, optional consumer quota wiring, and response formatting. No socket or
external service is used by these tests. Identity is supplied by the trusted
upstream gateway; this does not prove JWT verification. The current router uses
status-only responses and does not wire required scopes.

- Valid user and tenant: HTTP 200, empty body.
- User present but tenant absent: HTTP 403, empty body.
- User absent: HTTP 401, empty body.
- Quota enabled, one request per minute: first request 200, second 429.
- Same quota with enforcement disabled: both requests 200.
- Existing route test: valid `/authz` succeeds and `/mcp` returns 404.

This is an in-process authorization proof, not evidence of a same-pod deployment,
third-party gateway integration, upstream forwarding, or production capacity.
The topology distinctions in `specs/gateway-sidecar-contract.md` still apply.

## Commands and results

Commands below run from `stoa-gateway/` unless specified otherwise.
`cmake` is available at `/opt/homebrew/bin/cmake`; tests use default features for
the lean binary. Clippy uses the exact feature set selected by
`.github/workflows/stoa-gateway-ci.yml`, rather than all optional features.

```sh
cargo fmt --manifest-path stoa-gateway/Cargo.toml # from repository root
cargo fmt --check
cargo test --locked --lib sidecar -- --test-threads=1
RUSTFLAGS=-Dwarnings cargo clippy --locked --all-targets --features kafka,pingora,phases -- -D warnings
cargo build --locked --release
target/debug/deps/stoa_gateway-c445949ac79e95f5 mode::decision --test-threads=1
/usr/bin/time -l target/debug/deps/stoa_gateway-c445949ac79e95f5 sidecar --test-threads=1
stat -f '%z bytes' target/release/stoa-gateway
shasum -a 256 target/release/stoa-gateway
file target/release/stoa-gateway
git diff --check # from repository root
```

- Format and whitespace checks: passed.
- Default-feature sidecar selection: 36 passed, 0 failed (including both new tests).
- Shared decision engine: 5 passed, 0 failed.
- Direct timed sidecar rerun: 36 passed, 0 failed.
- Release build: passed, default features, optimized profile.
- Clippy: passed with CI features and warnings denied.

## Footprint and limitations

- Release binary: **33,823,088 bytes**, Mach-O 64-bit arm64.
- Binary SHA-256: `0fe6261f7766f147f2b691bfed2e4317ebbaab9182c4dc5bfa9ac846b65cf264`.
- Peak RSS: **40,501,248 bytes**, reported as `maximum resident set size` by
  macOS `/usr/bin/time -l` around the direct test executable, one sequential run
  of the 36 sidecar-selected tests (0.19 seconds wall time).

RSS includes the debug Rust test harness and its fixtures. It excludes compiler
and Cargo memory because the executable was invoked directly. It is not the
RSS of a release server, an idle deployment, or sustained traffic. The release
binary size includes all default-feature modes, not a sidecar-only executable.

No container was built. No image size, live gateway RSS, sustained-load figure,
certification, or comparison with another product is claimed.
