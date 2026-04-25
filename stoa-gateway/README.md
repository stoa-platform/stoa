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
- Optional: `cmake` (`brew install cmake`) for `cargo test --all-features`

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

## Dependencies

- **Depends on**: control-plane-api (config/tool sync), Keycloak (JWT verification)
- **Depended on by**: portal (MCP API consumer)
