# CAB-2173 Implementation Inventory

Date: 2026-04-25
Ticket: CAB-2173

## Runtime

| Area | Result |
|------|--------|
| Gateway binary | Same Rust `stoa-gateway` binary for `edge-mcp`, `sidecar`, `proxy`, and `shadow` modes. |
| Sidecar route profile | `STOA_GATEWAY_MODE=sidecar` mounts `POST /authz` plus health/readiness/metrics/admin routes. MCP routes are not mounted. |
| Shared decision path | `mode::decision::DecisionEngine` owns identity, tenant, consumer rate limit, and scope decisions. `mode::sidecar::SidecarService` is now an adapter around that engine. |
| Quota wiring | Sidecar router wires `AppState.consumer_rate_limiter` only when `quota_enforcement_enabled=true`. |

## Deployment Topologies

| File | Classification | Change |
|------|----------------|--------|
| `charts/stoa-platform/templates/stoa-sidecar-deployment.yaml` | Real same-pod sidecar | Requires `stoaSidecar.mainGateway.enabled=true`, renders target gateway container plus `stoa-sidecar`, labels `stoa.io/deployment-kind=sidecar`, annotates `stoa.io/topology=same-pod-sidecar`. |
| `charts/stoa-platform/values.yaml` | Real same-pod sidecar values | Documents same-pod scope, same binary route profile, and sidecar resource envelope (`50m`/`64Mi` request, `200m`/`256Mi` limit). |
| `k8s/gateways/base/stoa-link-wm/deployment.yaml` | Standalone remote link | Explicitly labelled `standalone-link`; no longer presents itself as a Kubernetes sidecar. Replaces unused `STOA_SIDECAR_UPSTREAM_URL` with `STOA_TARGET_GATEWAY_URL`. |
| `deploy/k3d/kong-sidecar.yaml` | Standalone authz demo | Reframed as `stoa-authz` standalone `/authz` endpoint on node port `30082`; comments and labels no longer claim sidecar topology. |
| `scripts/traffic/link-traffic-seed.sh` | Standalone authz traffic seed | Renames the Kong authz URL variable while preserving `LINK_KONG_URL` compatibility. |

## Docs

| File | Update |
|------|--------|
| `specs/gateway-sidecar-contract.md` | Durable LLM-readable contract for real sidecar vs standalone link/authz semantics, runtime invariants, Helm invariants, agent guardrails, and acceptance tests. |
| `stoa-gateway/README.md` | Adds deployment mode matrix, same-binary sidecar profile, shared decision engine note, and lean sidecar resource guidance. |
| `charts/stoa-platform/README.md` | Documents that Helm sidecar requires a target gateway container and fails standalone renders. |
| `docs/guides/gateway-auto-registration.md` | Distinguishes same-pod sidecar from standalone link deployments. |
| `docs/integrations/webmethods-sidecar-integration.md` | Clarifies real webMethods same-pod sidecar topology and shared decision pipeline. |

## Scope Guardrails

- No service-mesh controller or injection webhook added in this ticket.
- No new Rust crate or Kubernetes dependency added.
- Existing edge MCP routes are not changed.
- Standalone link topologies remain supported, but are labelled as standalone rather than sidecar.
