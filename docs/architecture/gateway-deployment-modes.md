# Gateway Deployment Modes

> **Status**: descriptive snapshot of `main` on 2026-11-05.
> **Scope**: where the STOA runtime sits relative to the gateway that serves
> traffic, and what the repository actually implements today. This page is not
> a support, compatibility or certification statement.
> **Normative sources**: [`specs/gateway-topology-normalization.md`](../../specs/gateway-topology-normalization.md)
> (vocabulary) and [`specs/gateway-sidecar-contract.md`](../../specs/gateway-sidecar-contract.md)
> (sidecar proof rule). If this page disagrees with them, the specs win.

## At a Glance

| | Standalone gateway | Sidecar (companion) | External agent |
|---|---|---|---|
| `deployment_mode` | `edge` | `sidecar` | `connect` |
| `topology` | `native-edge` | `same-pod` | `remote-agent` |
| STOA runtime | `stoa-gateway` with `STOA_GATEWAY_MODE=edge-mcp` | `stoa-gateway` with `STOA_GATEWAY_MODE=sidecar` | `stoa-connect` (Go), or a standalone `stoa-gateway` link |
| Who serves client traffic | STOA | The third-party gateway | The third-party gateway |
| STOA role per request | Full gateway | Allow/deny answer on `POST /authz` before the gateway forwards | Not in the request path; syncs config to the gateway's admin API |
| Status today | Implemented, default mode | Runtime and Helm template implemented; no live third-party run recorded; no environment declares one | Implemented (`stoa-connect`); declared in GitOps desired state |

```text
Standalone            Sidecar (same pod)                 External agent
client                client                             client
  |                     |                                  |
  v                     v                                  v
stoa-gateway          +-------------------------------+  third-party gateway <--admin API-- stoa-connect
  |                   | third-party gw --localhost--> |    |                                   |
  v                   |   |        stoa-sidecar /authz|    v                                   v
backend               +---|---------------------------+  backend                        Control Plane
                          v
                        backend
```

## Runtime Mode Is Not Deployment Mode

Two independent settings are often confused:

- **Runtime mode** (`STOA_GATEWAY_MODE`: `edge-mcp`, `sidecar`, `proxy`,
  `shadow`) selects the route profile of the Rust binary. It is read into
  `Config.gateway_mode` ([`stoa-gateway/src/config.rs`](../../stoa-gateway/src/config.rs))
  and dispatched in [`stoa-gateway/src/lib.rs`](../../stoa-gateway/src/lib.rs).
  [`stoa-gateway/src/mode/mod.rs`](../../stoa-gateway/src/mode/mod.rs) also
  contains `ModeConfig::from_env()`, which reads `STOA_MODE`; only unit tests
  call it. Use `STOA_GATEWAY_MODE`.
- **Deployment mode** (`deployment_mode`, `target_gateway_type`, `topology`)
  describes where the runtime sits. The gateway reports it to the Control Plane
  through `STOA_DEPLOYMENT_MODE`, `STOA_TARGET_GATEWAY_TYPE` and `STOA_TOPOLOGY`.

A runtime in `sidecar` mode is not automatically a sidecar deployment.
[`k8s/gateways/base/stoa-link-wm/deployment.yaml`](../../k8s/gateways/base/stoa-link-wm/deployment.yaml)
runs `STOA_GATEWAY_MODE=sidecar` but is a standalone link, so it is classified
`connect` / `remote-agent`. Only the same-pod proof rule (below) makes a
deployment `sidecar`.

## Standalone Gateway (`edge`)

**What it is.** `stoa-gateway` is the gateway. Clients and agents call it
directly; it routes to backends itself.

**Implemented today.**

- `edge-mcp` is the default `GatewayMode` and the Helm default
  (`stoaGateway.mode` in
  [`stoa-gateway-deployment.yaml`](../../charts/stoa-platform/templates/stoa-gateway-deployment.yaml)).
- Its route profile in `lib.rs` includes the MCP endpoints (`/mcp`, SSE,
  WebSocket, REST tool routes), OAuth discovery and proxy endpoints, LLM proxy
  routes, API proxying (`/proxy/*path` and a dynamic proxy fallback) and A2A
  routes.
- GitOps desired state declares `edge` / `native-edge` instances in the
  staging and production overlays
  ([example](../../k8s/gateways/overlays/production/gateway-instances.yaml)).

**Not covered here.** `proxy` and `shadow` are selectable runtime modes but are
not deployment topologies. The header of `mode/mod.rs` still labels them
planned. In `proxy` mode the router starts with an empty
`mode::proxy::RouteRegistry`; in `shadow` mode `/shadow/generate` uses a
hard-coded API id and URL.

## Sidecar / Companion (`sidecar`)

**What it is.** A third-party gateway keeps serving traffic. Before forwarding
to the backend, it calls a STOA container in the same Kubernetes pod at
`http://localhost:8081/authz`. STOA returns allow or deny.

**Proof rule** ([topology spec §4](../../specs/gateway-topology-normalization.md)):
a deployment is `sidecar` only if it is declared in Kubernetes desired state,
its pod contains the target gateway container and `stoa-sidecar`, and the
target gateway calls STOA over `localhost` or `127.0.0.1`. Otherwise classify it
as `connect` / `remote-agent`.

**Implemented today.**

- Sidecar mode mounts `POST /authz` plus operational routes, and no MCP routes.
  The test `sidecar_mode_exposes_authz_without_mcp_routes` in `lib.rs` covers
  this.
- `/authz` delegates to `DecisionEngine`
  ([`mode/decision.rs`](../../stoa-gateway/src/mode/decision.rs)): missing
  principal returns 401, missing tenant returns 403, and the consumer rate limit
  (429) applies only when `quota_enforcement_enabled=true`. Scope checks run
  only if required scopes are set on the engine; the `/authz` router sets none.
  OPA evaluation and Kafka metering are not part of `DecisionEngine`.
- `/authz` trusts the user and tenant sent by the calling gateway; it does not
  validate a token. The Helm template binds STOA to `127.0.0.1:8081` and does
  not expose that port through the Service.
- `SidecarSettings::from_env()` always selects the `StatusCode` response format.
  The JSON, Envoy ext_authz and Kong formatters in
  [`mode/sidecar.rs`](../../stoa-gateway/src/mode/sidecar.rs) are unit tested
  but no configuration selects them.
- Separately, an optional Envoy gRPC ext_authz listener
  ([`authz/ext_authz_grpc.rs`](../../stoa-gateway/src/authz/ext_authz_grpc.rs))
  starts when `ext_authz_grpc_addr` is configured, in any runtime mode. It
  validates JWTs itself and reuses `DecisionEngine`. In `prod` it requires
  `STOA_EXT_AUTHZ_AUDIENCE` and non-empty `STOA_EXT_AUTHZ_REQUIRED_SCOPES`. No
  example manifest in the repository enables it.
- The Helm template
  [`stoa-sidecar-deployment.yaml`](../../charts/stoa-platform/templates/stoa-sidecar-deployment.yaml)
  renders the target gateway container plus `stoa-sidecar`, and fails when
  `stoaSidecar.mainGateway.enabled` is false. `stoaSidecar.enabled` defaults to
  `false`.

**Not proven or planned.**

- The 2026-04-25 audit
  ([verification](../audits/2026-04-25-sidecar-deployment-reality/02-verification.md))
  proved the route split with Rust tests and the topology with `helm template`.
  It ran no live webMethods or Kong smoke test and built no container image.
- Whether a given gateway honours the injected variables (`EXT_AUTHZ_URL` in the
  chart, `apigw_ext_authz_*` in the
  [webMethods sidecar guide](../integrations/webmethods-sidecar-integration.md))
  is not demonstrated in the repository. The `stoa_sidecar_*` metric names in
  that guide do not appear in the gateway source.
- No `GatewayInstance` in `k8s/gateways/overlays/*/gateway-instances.yaml`
  declares `deploymentMode: sidecar`.
- No service-mesh injection or controller exists (audit scope guardrail).
- The gateway list in the `mode/sidecar.rs` header (Envoy, Kong, NGINX, Apigee,
  AWS) describes design targets, not tested integrations.

## External Agent (`connect`)

**What it is.** STOA runs as a separate process next to, but outside, the
third-party gateway. It talks to the gateway's admin API and to the Control
Plane. It is not in the request path; the third-party gateway enforces what
STOA pushes to it.

**Implemented today.**

- `stoa-connect` ([`stoa-go/cmd/stoa-connect`](../../stoa-go/cmd/stoa-connect/main.go),
  ADR-057) registers with the Control Plane as `connect`, sends heartbeats,
  discovers APIs, and syncs routes (SSE or polling), policies and credentials.
  Adapters for webMethods, Kong, Gravitee and Envoy live in
  [`stoa-go/internal/connect/adapters/`](../../stoa-go/internal/connect/adapters/adapter.go).
  Design: [`connect-architecture.md`](../../stoa-go/docs/connect-architecture.md).
- A standalone `stoa-gateway` link targeting a remote gateway
  (`stoa-link-wm`, labelled `stoa.io/deployment-kind=standalone-link`) is also
  classified `connect`.
- Most `GatewayInstance` entries in the dev, staging and production overlays
  are `connect` / `remote-agent` (webMethods, Kong, Gravitee, agentgateway).

**Limits.** Open follow-ups, such as a full re-push on SSE reconnect and a
possible double acknowledgement, are tracked in
[`connect-known-issues.md`](../../stoa-go/docs/connect-known-issues.md).

## Example Files by Mode and Maturity

Maturity labels:

- **GitOps**: Kubernetes desired state in `k8s/gateways/` (dev and staging
  overlays are Argo CD sources in
  [`deploy/k3s-gateways/argocd.yaml`](../../deploy/k3s-gateways/argocd.yaml)).
- **Chart**: Helm template; "render-verified" means proven only by
  `helm template`.
- **Local demo**: Docker or k3d; simplified or fake authentication; not for
  production.
- **Legacy demo**: kept for local traffic seeding; the name predates the current
  vocabulary.

No workflow under `.github/` references the compose files, the k3d manifest,
`stoa-link-wm` or the `stoaSidecar` values.

| File | STOA runtime | Mode | Maturity | Notes |
|------|--------------|------|----------|-------|
| [`charts/.../stoa-gateway-deployment.yaml`](../../charts/stoa-platform/templates/stoa-gateway-deployment.yaml) | `stoa-gateway`, `edge-mcp` by default | Standalone | Chart | Main gateway Deployment. |
| [`k8s/gateways/base/stoa-gateway/deployment.yaml`](../../k8s/gateways/base/stoa-gateway/deployment.yaml) | `edge-mcp` | Standalone | GitOps | Included by the dev, staging and production overlays. |
| [`k8s/gateways/overlays/demo/workloads.yaml`](../../k8s/gateways/overlays/demo/workloads.yaml) | default (`edge-mcp`) | Standalone | Demo overlay | In-pod nginx only filters paths; it does not call `/authz`. `test_runtime.py` tests the demo helper scripts, not the gateway. |
| [`deploy/vps/stoa-gateway/docker-compose.staging.yml`](../../deploy/vps/stoa-gateway/docker-compose.staging.yml) | `edge-mcp` | Standalone | VPS compose | Single gateway container. |
| [`deploy/docker-compose/docker-compose.yml`](../../deploy/docker-compose/docker-compose.yml), service `stoa-gateway` | `edge-mcp` | Standalone | Local demo | Full local stack. |
| Same file, service `stoa-gateway-connect` | `edge-mcp` | Standalone, behind nginx | Local demo | nginx simulates a third-party gateway. Not the `stoa-connect` agent. |
| Same file, services `stoa-gateway-link` + `link-proxy` | `sidecar` | Companion on a Docker network, not a Kubernetes sidecar | Local demo | nginx calls `/authz` before forwarding; any `Bearer` value becomes a fixed demo principal. |
| [`deploy/docker-compose/docker-compose.sidecar.yml`](../../deploy/docker-compose/docker-compose.sidecar.yml) | `sidecar` | Companion on a Docker network, not a Kubernetes sidecar | Local demo | Same fixed demo principal. See its [README](../../deploy/docker-compose/sidecar/README.md); its response-format note describes intent, not current wiring. |
| [`charts/.../stoa-sidecar-deployment.yaml`](../../charts/stoa-platform/templates/stoa-sidecar-deployment.yaml) | `sidecar` | Sidecar (same pod) | Chart, render-verified | Only manifest meeting the proof rule. Disabled by default; no live run recorded. |
| [`deploy/k3d/kong-sidecar.yaml`](../../deploy/k3d/kong-sidecar.yaml) | `sidecar` (`stoa-authz`) | Standalone authz endpoint, not a sidecar | Legacy demo | Kong does not call STOA before forwarding. |
| [`k8s/gateways/base/stoa-link-wm/deployment.yaml`](../../k8s/gateways/base/stoa-link-wm/deployment.yaml) | `sidecar` | External agent (standalone link) | GitOps | Labelled `standalone-link`. |
| [`deploy/docker-compose/docker-compose.webmethods.yml`](../../deploy/docker-compose/docker-compose.webmethods.yml), service `stoa-connect` | `stoa-connect` (Go) | External agent | Local demo | Its `STOA_GATEWAY_MODE: "connect"` is not read by `stoa-connect` and is not a valid `stoa-gateway` mode. |
| [`k8s/gateways/overlays/*/gateway-instances.yaml`](../../k8s/gateways/overlays/production/gateway-instances.yaml) | None (`GatewayInstance` declarations) | `edge` and `connect` only | GitOps | No `sidecar` entry. |
| [`deploy/vps/webmethods/`](../../deploy/vps/webmethods/docker-compose.yml) compose files, [`k8s/arena/`](../../k8s/arena/kong.yaml) gateways | None | Not applicable | Out of scope | Third-party gateway only; no STOA runtime in the file. |

## Sources

- Code: [`stoa-gateway/src/mode/`](../../stoa-gateway/src/mode/mod.rs),
  `stoa-gateway/src/lib.rs`, `stoa-gateway/src/main.rs`,
  `stoa-gateway/src/config.rs`, `stoa-go/internal/connect/`.
- Specs: [`gateway-sidecar-contract.md`](../../specs/gateway-sidecar-contract.md),
  [`gateway-topology-normalization.md`](../../specs/gateway-topology-normalization.md).
- Audit (point-in-time):
  [`00-council-preflight.md`](../audits/2026-04-25-sidecar-deployment-reality/00-council-preflight.md),
  [`01-implementation-inventory.md`](../audits/2026-04-25-sidecar-deployment-reality/01-implementation-inventory.md),
  [`02-verification.md`](../audits/2026-04-25-sidecar-deployment-reality/02-verification.md).
- Existing guides: [webMethods sidecar integration](../integrations/webmethods-sidecar-integration.md),
  [Docker sidecar demo](../../deploy/docker-compose/sidecar/README.md),
  [gateway auto-registration](../guides/gateway-auto-registration.md).
