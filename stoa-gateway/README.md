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

### Memory backpressure

| Variable | Behavior |
| --- | --- |
| `STOA_MEMORY_LIMIT_MB` | Optional memory budget in MiB. The gateway uses the finite Linux cgroup limit when the budget is omitted and caps an explicit budget at that limit. If neither provides a budget, it uses 512 MiB. The YAML key `memory_limit_mb` can also set an explicit budget. |
| `STOA_MEMORY_BACKPRESSURE_HIGH_RATIO` | Starts shedding when process RSS reaches this fraction of the effective budget. Defaults to `0.80`. |
| `STOA_MEMORY_BACKPRESSURE_LOW_RATIO` | Stops shedding when process RSS falls below this fraction of the effective budget. Defaults to `0.70`. |
| `STOA_BACKPRESSURE_LIVENESS_FAIL_AFTER_SECS` | `/health/live` returns `503` after this many continuous seconds of shedding. Defaults to `300`. Set to `0` to disable the memory check on liveness. |

Leave the memory budget unset on Kubernetes to use the container limit. The
startup log records the effective budget, its source and both RSS thresholds.
`/health` answers `200` while the process can respond. `/health/ready` (alias
`/ready`) returns `503` as soon as shedding starts, in addition to its existing
readiness checks. Recovery below the low watermark resets the liveness timer.

### Standalone contract publishing

Set `STOA_STANDALONE=true` to disable control plane registration, heartbeats,
remote API key validation, and remote route reload. Leave `STOA_CONTROL_PLANE_URL`
unset or blank. The gateway refuses to start when both are configured. The admin
contract endpoints remain available through the usual admin authentication. The
standalone flag defaults to `false`.

`STOA_CONTRACT_STATE_PATH` sets the contract snapshot file. In standalone mode it
defaults to `contracts.json` in the working directory. Setting the path also
enables persistence in connected mode. Use a writable directory on a persistent
volume and give each gateway process its own snapshot file. The gateway saves
contract changes atomically and restores bindings before listening. A missing
file starts with an empty registry. An unreadable or invalid snapshot prevents
startup.

### Per-consumer REST quotas

In `edge-mcp` mode, the gateway always enforces a published REST contract's
`consumer_quota` policy. `STOA_QUOTA_ENFORCEMENT_ENABLED` controls the generic
quota middleware independently. When pushing a contract to `/admin/contracts`,
include `inbound_auth: "jwt"` (or a JWT policy) and a `consumer_quota` policy
in `policies`. Configure the JWT issuer through `STOA_KEYCLOAK_URL` and set the
expected audience with `inbound_auth_audience` on the contract. The default REST
audience uses `STOA_KEYCLOAK_CLIENT_ID`, which defaults to `stoa-mcp-gateway`.

```json
{
  "type": "consumer_quota",
  "config": {
    "consumers": [
      {"consumer_id": "catalog-reader", "rate_limit_per_minute": 5}
    ]
  }
}
```

Each consumer ID must be unique and each cap must be a positive integer.
The gateway matches the verified JWT `azp` claim to `consumer_id` after checking
the JWT and tenant. Missing or unlisted consumer IDs receive `403`.

All endpoints of a published REST contract share a fixed 60-second window for
each tenant, contract, JWT issuer, and consumer. The first admission opens the
window. Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset` (Unix seconds). Calls above the cap receive `429` with
`Retry-After` in seconds. Contract updates keep the current window's usage.
Restarting restores contracts and caps and starts fresh counters. Each replica
counts requests independently.

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
The gateway remembers the tenant UUID and highest accepted version for its
process lifetime (at most 10,000 tenants); it refuses version rollback or
replacement under the same tenant name. Issuance times may differ between
Control Plane replicas serving the same or a newer version; signed lifetime and
future clock-skew bounds still apply. These checks do not establish an initial
version floor and do not survive a restart. Use authenticated transport and
environment-specific issuer/audience values when connecting to the Control Plane.
Artifacts are limited to 1 MiB and at most one hour of signed validity.

Before rollout, provision the Control Plane signing key and key identifier,
mount the corresponding gateway trust file, and configure startup policy tenants.
The signing endpoint and an initial signed policy must be available to the gateway.
Without those inputs the gateway deliberately remains unready and denies calls.
