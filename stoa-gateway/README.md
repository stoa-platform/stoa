# STOA Gateway

Rust implementation of the unified STOA gateway. Implements the 4-mode architecture (ADR-024): edge-mcp, sidecar, proxy, shadow.

## Tech Stack

- Rust 2021 edition, Tokio 1 (async runtime), Axum 0.7 (web framework)
- serde/serde_json, Figment (layered config: YAML + env)
- jsonwebtoken 10, reqwest 0.12 (HTTP client)
- moka 0.12 (in-memory cache), prometheus 0.13

## Prerequisites

- Rust stable toolchain
- Optional: `librdkafka` (`brew install librdkafka`) for Kafka feature
- `cmake` is required for `cargo test --all-features` (the Kafka dependency builds native code).
  Install with `brew install cmake` on macOS, or your Linux package manager
  (for example, `sudo apt-get install cmake` on Debian/Ubuntu).

## Quick Start

```bash
cp .env.example .env           # Edit STOA_KEYCLOAK_URL, STOA_CONTROL_PLANE_URL
cargo run                      # Runs on http://localhost:8080
```

## Commands

```bash
cargo check              # Fast compile check
cargo test               # Run tests (default features)
cargo test --all-features # Run tests including kafka (requires cmake)
cargo clippy             # Lint
cargo fmt --check        # Format check
cargo run                # Run server
```

From the repository root, run `make test-gateway-all-features` to check that
`cmake` is installed before running `cargo test --all-features`.
Use `make test-gateway` for default-feature tests, which do not require `cmake`.

## Project Structure

```
src/
├── main.rs              # Entry point + Axum router setup
├── config.rs            # Figment-based layered configuration
├── state.rs             # AppState (shared application state)
├── auth/                # API key auth, OAuth2, Keycloak OIDC
├── control_plane/       # Client for control-plane-api
├── mcp/                 # MCP protocol (discovery, session, SSE, tools)
├── proxy/               # Dynamic proxy, SSRF protection
├── routes/              # Route definitions
└── uac/                 # Universal API Contract
tests/
├── integration/         # TestApp-based integration tests
├── contract/            # Snapshot-based contract tests (insta)
├── resilience/          # Circuit breaker, fault injection
├── security/            # Auth, headers, SSRF tests
└── e2e/                 # Docker-based end-to-end tests
```

## Feature Flags

| Feature | Crate | Purpose | Build Dep |
|---------|-------|---------|-----------|
| `kafka` | rdkafka | Kafka metering | cmake, libsasl2-dev |
| `k8s` | kube, k8s-openapi | K8s CRD watcher | None |

Default features: **none** (lean community build).

The published gateway image enables `kafka,pingora,k8s` to support the Helm
environment profiles. Policy evaluation is always compiled in; it does not
require a `tenant-policy` Cargo feature. Helm CI checks rendered capability
switches against the image build arguments and verifies Rust CI coverage.

```bash
cargo build --release                          # Community
cargo build --release --features "kafka,k8s"   # Enterprise
```

## Deployment Modes

The gateway ships as one Rust binary with route profiles selected by
`STOA_GATEWAY_MODE`.

| Mode | Routes | Intended topology |
|------|--------|-------------------|
| `edge-mcp` | MCP/SSE/tool routes plus health/admin/metrics | STOA native gateway |
| `sidecar` | `POST /authz` plus health/admin/metrics | Same-pod sidecar for Kong, Envoy, webMethods, Apigee |
| `proxy` | Inline proxy routes | Micro-gateway path |
| `shadow` | Passive capture routes | Mesh/tap analysis |

Sidecar mode does not mount MCP routes. It adapts third-party gateway authz
calls into the shared `mode::decision::DecisionEngine`, so sidecar,
micro-gateway, and mesh adapters can reuse identity, tenant, quota, and scope
decisions instead of duplicating policy logic.

For a lean sidecar image, build with the default feature set unless Kafka or
Kubernetes watchers are required. The Helm sidecar defaults reserve a small
runtime envelope (`50m` CPU / `64Mi` memory request, `200m` / `256Mi` limit)
and should be re-measured for each release image.

## Configuration

All settings via `STOA_*` env vars or `config.yaml`. See `.env.example` for the full list.

Key variables:
- `STOA_KEYCLOAK_URL` / `STOA_KEYCLOAK_REALM` — Authentication
- `STOA_CONTROL_PLANE_URL` — Control Plane API for tool sync
- `STOA_GATEWAY_MODE` — Deployment mode (edge-mcp, sidecar, proxy, shadow)
- `STOA_MCP_AUDIENCE` — Audience required on MCP tokens. No default; the gateway refuses to start in `prod` without it
- `STOA_KEYCLOAK_CLIENT_KEY_PATH` / `STOA_KEYCLOAK_CLIENT_KEY_ID` — Service identity using `private_key_jwt` (RFC 7523). Mount the key file from a Kubernetes Secret; its content is never logged
- `STOA_SERVICE_TOKEN_MAX_TTL_SECS` — Upper bound on the cached service-token lifetime (default 300)

Tools are denied by default: a tenant can call a tool only when the Control Plane
returns an explicit allow for it. Without a `private_key_jwt` service identity, the
gateway cannot read tool permissions and every tool call is denied.

## Dependencies

- **Depends on**: control-plane-api (config/tool sync), Keycloak (JWT verification)
- **Depended on by**: portal (MCP API consumer)

### Signed tool permissions

Tool calls require an explicit allow from the Control Plane's complete signed
policy (`GET /v1/tenants/{tenant}/tool-permissions/artifact`). Configure
`STOA_POLICY_TRUST_JWKS_FILE` with the pinned Ed25519 public keys and use
`STOA_POLICY_EXPECTED_ISSUER` / `STOA_POLICY_AUDIENCE` to bind the policy to
this gateway. The signed `expires_at` timestamp is required and must be in the
future; it also bounds cache validity and policy readiness. Policies are renewed
before expiry using a 30-second margin and the endpoint's `reissue=true` option.
Cached artifacts are reverified against the loaded trust set. The trust file is
loaded at startup; changing its keys requires a gateway restart. An absent or invalid artifact or
trust set denies calls; the unsigned permissions listing is never a fallback.
The gateway remembers the tenant UUID and highest accepted version and issuance
time for its process lifetime (at most 10,000 tenants); it refuses rollback or
replacement under the same tenant name. These checks do not establish an initial
version floor and do not survive a restart. Use authenticated transport and
environment-specific issuer/audience values when connecting to the Control Plane.
Artifacts are limited to 1 MiB and at most one hour of signed validity.

Before rollout, provision the Control Plane signing key and key identifier,
mount the corresponding gateway trust file, and configure startup policy tenants.
The signing endpoint and an initial signed policy must be available to the gateway.
Without those inputs the gateway deliberately remains unready and denies calls.
