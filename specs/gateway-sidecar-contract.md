# STOA Gateway Sidecar Contract

> **Status**: v0.1 — 2026-04-25.
> **Ticket**: CAB-2173.
> **Purpose**: freeze the LLM-readable contract for real STOA sidecar deployment
> semantics, distinct from standalone links and standalone authz demos.
> **Topology model**: see `specs/gateway-topology-normalization.md` for the
> canonical CP/Console fields: `deployment_mode`, `target_gateway_type`,
> `topology`.

## 1. LLM Contract Summary

```yaml
contract:
  id: gateway-sidecar-contract
  ticket: CAB-2173
  owner_component: stoa-gateway
  stable_terms:
    real_sidecar: "A third-party gateway container and a stoa-sidecar container in the same Kubernetes pod."
    standalone_link: "A STOA process targeting a remote gateway; valid topology, but not a Kubernetes sidecar."
    standalone_authz: "A standalone /authz endpoint for local tests; valid demo, but not a sidecar."
  primary_runtime:
    binary: stoa-gateway
    env_mode: STOA_GATEWAY_MODE=sidecar
    routes:
      required:
        - "POST /authz"
        - "GET /health"
        - "GET /ready"
        - "GET /metrics"
      forbidden:
        - "/mcp"
        - "/mcp/*"
  decision_pipeline:
    shared_engine: "stoa-gateway/src/mode/decision.rs::DecisionEngine"
    adapter: "stoa-gateway/src/mode/sidecar.rs::SidecarService"
    adapter_rule: "Protocol adapters convert input into DecisionInput; they do not duplicate identity, tenant, quota, or scope policy logic."
  helm_contract:
    template: "charts/stoa-platform/templates/stoa-sidecar-deployment.yaml"
    enabled_value: "stoaSidecar.enabled=true"
    hard_requirement: "stoaSidecar.mainGateway.enabled=true"
    failure_if_missing_main_gateway: true
    pod_topology_label: "stoa.io/deployment-kind=sidecar"
    pod_topology_annotation: "stoa.io/topology=same-pod-sidecar"
  standalone_contracts:
    webmethods_remote_link:
      file: "k8s/gateways/base/stoa-link-wm/deployment.yaml"
      label: "stoa.io/deployment-kind=standalone-link"
      note: "Must not be described as a Kubernetes sidecar."
    k3d_authz_demo:
      file: "deploy/k3d/kong-sidecar.yaml"
      resource_name: "stoa-authz"
      label: "stoa.io/deployment-kind=standalone-authz"
      note: "Kong does not call STOA before forwarding in this demo."
```

## 2. Contractual Definitions

### 2.1 Real Sidecar

A STOA sidecar is real only when:

- the third-party gateway container and `stoa-sidecar` container run in the same
  Kubernetes pod;
- the third-party gateway calls `http://localhost:8081/authz` or
  `http://127.0.0.1:8081/authz` before backend forwarding;
- the STOA container runs the same Rust binary with `STOA_GATEWAY_MODE=sidecar`;
- the pod is labelled as `stoa.io/deployment-kind=sidecar`.

If one of these conditions is missing, do not call the deployment a Kubernetes
sidecar.

### 2.2 Standalone Link

A standalone link is a STOA process that targets a remote gateway, for example a
webMethods instance on a VPS. This topology is valid for STOA Link/Connect, but
it is not a Kubernetes sidecar because it is not co-located with the gateway
container.

Standalone links must use an explicit label:

```yaml
stoa.io/deployment-kind: standalone-link
```

### 2.3 Standalone Authz Demo

A standalone authz demo exposes STOA `/authz` separately for local testing. It
must not imply that the upstream gateway calls STOA before backend forwarding
unless that call is actually configured and tested.

Standalone authz demos must use an explicit label:

```yaml
stoa.io/deployment-kind: standalone-authz
```

## 3. Runtime Invariants

| Invariant | Required behavior |
|-----------|-------------------|
| Same binary | `stoa-gateway` is reused for edge MCP, sidecar, proxy, and shadow modes. |
| Sidecar route surface | Sidecar mode mounts `/authz` and operational routes only. MCP routes are absent. |
| Shared decision logic | Sidecar calls `DecisionEngine`; future micro-gateway and mesh adapters must reuse the same engine. |
| Optional quota | Consumer rate limiting is wired into sidecar only when `quota_enforcement_enabled=true`. |
| Response adapters | Envoy/Kong/status/JSON formatting remains in `SidecarService`; policy decisions remain in `DecisionEngine`. |

### 3.1 Model Alignment

For CP/API/Console models, do not introduce a separate `deployment_kind` field.
Use the canonical topology fields from `gateway-topology-normalization.md`:

```yaml
deployment_mode: sidecar
target_gateway_type: kong | webmethods | gravitee | agentgateway
topology: same-pod
```

Kubernetes labels such as `stoa.io/deployment-kind=sidecar` are deployment
metadata only; they are not the product data model.

## 4. Helm Invariants

| Invariant | Required behavior |
|-----------|-------------------|
| No fake sidecar render | `stoaSidecar.enabled=true` with `stoaSidecar.mainGateway.enabled=false` must fail Helm rendering. |
| Same-pod proof | Rendered sidecar Deployment contains the target gateway container and `stoa-sidecar`. |
| Authz URL | Target gateway env includes `EXT_AUTHZ_URL=http://localhost:8081/authz` unless overridden by a gateway-specific equivalent. |
| STOA binding | STOA sidecar binds `STOA_HOST=127.0.0.1` and `STOA_PORT=8081` by default. |
| Service exposure | The Service exposes the main gateway port, not a public sidecar authz port. |

## 5. Agent Guardrails

When an LLM or coding agent touches sidecar-related code or manifests:

1. Do not rename standalone link/authz topologies to sidecar unless they are
   actually same-pod deployments.
2. Do not add MCP routes to `GatewayMode::Sidecar`.
3. Do not duplicate authorization checks in a new adapter. Add fields to
   `DecisionInput`/`Decision` if the shared pipeline needs more context.
4. Do not make Kafka, Kubernetes watchers, or Pingora required for a lean
   sidecar build unless a new ticket explicitly changes the footprint contract.
5. Do not remove Helm's `mainGateway.enabled=true` guardrail without replacing
   it with another proof that the rendered topology is a real sidecar.

## 6. Acceptance Tests

| ID | Test | PASS condition |
|----|------|----------------|
| GSC-1 | `cargo test mode::decision` | Shared decision engine tests pass. |
| GSC-2 | `cargo test mode::sidecar` | Sidecar adapter and response format tests pass. |
| GSC-3 | `cargo test sidecar_mode_exposes_authz_without_mcp_routes` | `/authz` returns success for valid input and `/mcp` returns 404 in sidecar mode. |
| GSC-4 | `helm template ... --set stoaSidecar.enabled=true --set stoaSidecar.mainGateway.enabled=true` | Rendered Deployment contains both gateway and `stoa-sidecar` containers. |
| GSC-5 | `helm template ... --set stoaSidecar.enabled=true --set stoaSidecar.mainGateway.enabled=false` | Rendering fails with the topology guardrail message. |
| GSC-6 | Search touched standalone manifests for fake-sidecar wording | No misleading claim remains that standalone k3d/webMethods link manifests are same-pod sidecars. |

## 7. Evidence

Current CAB-2173 evidence:

- `docs/audits/2026-04-25-sidecar-deployment-reality/01-implementation-inventory.md`
- `docs/audits/2026-04-25-sidecar-deployment-reality/02-verification.md`

This spec is the durable contract. The audit files are point-in-time evidence.
