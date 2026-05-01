# Gateway Topology Normalization

> **Status**: v0.2 — 2026-05-01.
> **Purpose**: normalize existing data-plane gateways across dev, staging, and
> prod so STOA can choose the correct deployment path for edge, connect, and
> real sidecar gateways.
> **Related contract**: `specs/gateway-sidecar-contract.md`.

## 1. LLM Contract Summary

```yaml
contract:
  id: gateway-topology-normalization
  canonical_fields:
    deployment_mode:
      enum: [edge, connect, sidecar]
      meaning:
        edge: 'Native STOA Gateway / Edge MCP runtime.'
        connect: 'Remote agent/link or standalone gateway connector.'
        sidecar: 'Same-pod Kubernetes sidecar for a third-party gateway.'
    target_gateway_type:
      enum: [stoa, kong, webmethods, gravitee, agentgateway]
      meaning: 'The gateway product STOA fronts, controls, or augments.'
    topology:
      enum: [native-edge, remote-agent, same-pod]
      meaning:
        native-edge: 'STOA is the gateway runtime.'
        remote-agent: 'STOA agent/link talks to a remote gateway.'
        same-pod: 'Gateway target and stoa-sidecar share one Kubernetes pod.'
  forbidden_fields:
    - gateway_family
    - deployment_kind
  identity_model:
    logical_gateway: 'One GatewayInstance per logical gateway.'
    endpoints:
      public_url: 'User/tenant reachable URL.'
      internal_url: 'Cluster/service URL for in-cluster calls.'
      admin_url: 'Control/admin endpoint.'
      health_url: 'Health/readiness endpoint when different from admin_url.'
  source_of_truth:
    desired_state: 'GitOps manifest'
    reconciliation: 'CP reconciles DB and Console from GitOps desired state.'
    db_patch_only: 'Forbidden except emergency repair with follow-up desired-state PR.'
```

## 2. Vocabulary

| Term      | Definition                                                            | Deployment path                |
| --------- | --------------------------------------------------------------------- | ------------------------------ |
| `edge`    | STOA Gateway native runtime, including Edge MCP.                      | Route registry / STOA Gateway. |
| `connect` | Remote agent/link or standalone connector to a third-party gateway.   | Pull agent + ack.              |
| `sidecar` | Real same-pod K8s sidecar: target gateway container + `stoa-sidecar`. | Same-pod local authz + ack.    |

Do not use `sidecar` as a generic term for "near a gateway". If same-pod proof
is missing, classify as `connect`.

## 3. Canonical Data Model

Use exactly these classification fields:

```yaml
deployment_mode: edge | connect | sidecar
target_gateway_type: stoa | kong | webmethods | gravitee | agentgateway
topology: native-edge | remote-agent | same-pod
```

Do not add separate `gateway_family` or `deployment_kind` fields in CP or
Console. UI labels and routing behavior derive from these three fields.

### 3.1 Logical Identity vs Network Endpoints

One logical `GatewayInstance` can have multiple endpoints:

```yaml
gateway:
  name: stoa-gateway-prod
  environment: prod
  deployment_mode: edge
  target_gateway_type: stoa
  topology: native-edge
  endpoints:
    public_url: https://mcp.gostoa.dev
    internal_url: http://stoa-gateway.stoa-system.svc.cluster.local
    admin_url: http://stoa-gateway.stoa-system.svc.cluster.local/admin
    health_url: http://stoa-gateway.stoa-system.svc.cluster.local/health
```

This prevents false duplicates such as `mcp.gostoa.dev` and
`stoa-gateway.stoa-system.svc.cluster.local:80` being treated as separate
gateways when they are only public and internal endpoints for the same logical
runtime.

## 4. Sidecar Proof Rule

A gateway can be classified as `deployment_mode=sidecar` only if all conditions
are true:

1. It is declared in Kubernetes desired state.
2. Its pod contains at least two containers.
3. One container is the target gateway (`kong`, `webmethods`, `gravitee`, or
   `agentgateway`).
4. One container is `stoa-sidecar`.
5. The target gateway calls STOA via `localhost` or `127.0.0.1`, normally
   `http://localhost:8081/authz`.

If any condition is not proven, classification is:

```yaml
deployment_mode: connect
topology: remote-agent
```

## 5. GitOps Desired State

Classification must be carried by desired state, not corrected only in DB.

```yaml
gateways:
  - name: stoa-gateway-prod
    environment: prod
    deployment_mode: edge
    target_gateway_type: stoa
    topology: native-edge
    endpoints:
      public_url: https://mcp.gostoa.dev
      internal_url: http://stoa-gateway.stoa-system.svc.cluster.local
      admin_url: http://stoa-gateway.stoa-system.svc.cluster.local/admin
      health_url: http://stoa-gateway.stoa-system.svc.cluster.local/health

  - name: connect-webmethods-prod
    environment: prod
    deployment_mode: connect
    target_gateway_type: webmethods
    topology: remote-agent
    endpoints:
      admin_url: http://connect-webmethods-prod:8090
      health_url: http://connect-webmethods-prod:8090/health

  - name: kong-sidecar-prod
    environment: prod
    deployment_mode: sidecar
    target_gateway_type: kong
    topology: same-pod
    proof:
      namespace: stoa-system
      deployment: kong-with-stoa-sidecar
      target_container: kong
      sidecar_container: stoa-sidecar
      authz_url: http://localhost:8081/authz
```

CP reconciles `GatewayInstance` rows and Console views from this desired state.
Emergency DB correction is allowed only as a temporary operational repair and
must be followed by a desired-state PR.

## 6. Current Gateway Inventory From Console

### 6.1 Production

| Current gateway                                 | Current label | Status  | Target classification               | Action                                                                              |
| ----------------------------------------------- | ------------- | ------- | ----------------------------------- | ----------------------------------------------------------------------------------- |
| `mcp.gostoa.dev`                                | STOA Edge MCP | Online  | `edge/stoa/native-edge`             | Merge as `public_url` of the logical prod edge if same runtime as internal service. |
| `stoa-gateway.stoa-system.svc.cluster.local:80` | Edge MCP      | Online  | `edge/stoa/native-edge`             | Merge as `internal_url` of the same logical prod edge if same runtime.              |
| `connect-kong:8090`                             | Connect       | Online  | `connect/kong/remote-agent`         | Keep.                                                                               |
| `connect-webmethods-prod:8090`                  | Connect       | Offline | `connect/webmethods/remote-agent`   | Repair heartbeat or archive if superseded.                                          |
| `gravitee-stoa-link:8081`                       | STOA Link     | Online  | `connect/gravitee/remote-agent`     | Reclassified in desired state until same-pod proof exists.                          |
| `webmethods-stoa-link:8081`                     | STOA Link     | Online  | `connect/webmethods/remote-agent`   | Reclassified in desired state until same-pod proof exists.                          |
| `kong-stoa-link:8081`                           | STOA Link     | Online  | `connect/kong/remote-agent`         | Reclassified in desired state until same-pod proof exists.                          |
| `agentgateway-stoa-link:8081`                   | STOA Link     | Online  | `connect/agentgateway/remote-agent` | Reclassified in desired state until same-pod proof exists.                          |
| `vps-wm-link-prod:9200`                         | STOA Link     | Offline | `connect/webmethods/remote-agent`   | Do not call sidecar; decide duplicate vs replacement for `connect-webmethods-prod`. |

### 6.2 Staging

| Current gateway                   | Current label | Status | Target classification             | Action                                                     |
| --------------------------------- | ------------- | ------ | --------------------------------- | ---------------------------------------------------------- |
| `connect-webmethods-staging:8090` | Connect       | Online | `connect/webmethods/remote-agent` | Keep.                                                      |
| `stoa-gateway-staging:8080`       | Edge MCP      | Online | `edge/stoa/native-edge`           | Keep.                                                      |
| `stoa-link-wm-staging:8080`       | STOA Link     | Online | `connect/webmethods/remote-agent` | Reclassified in desired state until same-pod proof exists. |

### 6.3 Development

| Current gateway               | Current label | Status | Target classification             | Action                                                     |
| ----------------------------- | ------------- | ------ | --------------------------------- | ---------------------------------------------------------- |
| `connect-webmethods-dev:8090` | Connect       | Online | `connect/webmethods/remote-agent` | Keep.                                                      |
| `stoa-link-wm-dev:8080`       | STOA Link     | Online | `connect/webmethods/remote-agent` | Reclassified in desired state until same-pod proof exists. |

## 7. Rollout Plan

### Phase 0 — Contract and data export

- Freeze this spec as the classification contract.
- Export current CP gateway rows with `id`, `name`, `environment`, `mode`,
  `gateway_type`, `public_url`, `admin_url`, `last_heartbeat`, `capabilities`.
- Export K8s desired/runtime state for current `*-stoa-link` workloads:
  namespace, deployment, pod containers, env vars, service names, labels.

### Phase 1 — Desired-state schema

- Add desired-state support for:
  - `deployment_mode`
  - `target_gateway_type`
  - `topology`
  - `endpoints.public_url`
  - `endpoints.internal_url`
  - `endpoints.admin_url`
  - `endpoints.health_url`
- Keep backwards compatibility with existing `mode`, `gateway_type`,
  `admin_url`, and `public_url` during one migration cycle.

### Phase 2 — CP reconciliation

- Reconcile `GatewayInstance` from GitOps desired state.
- Make logical identity stable by `environment + name`.
- Store endpoints as structured data or a compatible schema extension.
- Prevent DB-only classification drift: desired state wins unless emergency
  override is explicitly marked.

### Phase 3 — Topology proof

- Implement or script proof checks for sidecar candidates:
  - K8s object exists.
  - Pod has target gateway container and `stoa-sidecar`.
  - Target gateway env/config points to `localhost:8081/authz`.
- Write proof result to CP/Console as evidence, not just as a label.

### Phase 4 — Console normalization

- Display labels derived from canonical fields:
  - `edge/stoa/native-edge` -> `Edge`
  - `connect/*/remote-agent` -> `Connect`
  - `sidecar/*/same-pod` -> `Sidecar`
- Show all endpoints under one logical gateway detail page.
- Flag ambiguous `STOA Link` entries as `Needs topology proof`.

### Phase 5 — Environment rollout

1. Development:
   - classify `connect-webmethods-dev`;
   - audit `stoa-link-wm-dev`;
   - update Console labels.
2. Staging:
   - classify `connect-webmethods-staging`;
   - classify `stoa-gateway-staging`;
   - audit `stoa-link-wm-staging`;
   - run `/api-deployments` flow.
3. Production:
   - merge prod edge public/internal endpoints if they are the same runtime;
   - keep `connect-kong`;
   - repair/archive `connect-webmethods-prod` and `vps-wm-link-prod`;
   - audit and reclassify `gravitee`, `webmethods`, `kong`, `agentgateway`
     `*-stoa-link` entries one by one.

### Phase 6 — Deployment-path enforcement

Use topology to select deployment behavior:

| Classification           | Deployment path                                 |
| ------------------------ | ----------------------------------------------- |
| `edge/stoa/native-edge`  | Route registry / STOA Gateway.                  |
| `connect/*/remote-agent` | Pull agent + route-sync ack.                    |
| `sidecar/*/same-pod`     | Same-pod local authz plus route-sync ack/proof. |

`/api-deployments` must not infer the path from display labels or URL shape.

## 8. Acceptance Tests

| ID    | Test                                        | PASS condition                                                                                              |
| ----- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| GTN-1 | Desired state parses canonical fields       | `deployment_mode`, `target_gateway_type`, `topology`, and endpoint object validate.                         |
| GTN-2 | No redundant field introduced               | CP/API/Console do not add `gateway_family` or `deployment_kind` model fields.                               |
| GTN-3 | Edge endpoint merge                         | `mcp.gostoa.dev` and internal service can be represented as one logical prod edge with multiple endpoints.  |
| GTN-4 | Sidecar proof gate                          | A gateway cannot be `sidecar` unless same-pod K8s proof passes.                                             |
| GTN-5 | False sidecar fallback                      | A `*-stoa-link` without same-pod proof becomes `connect/*/remote-agent`.                                    |
| GTN-6 | Console labels derive from canonical fields | UI labels match `Edge`, `Connect`, or `Sidecar` from canonical classification.                              |
| GTN-7 | Deployment path derives from topology       | `/api-deployments` selects edge registry, connect pull+ack, or sidecar same-pod path from canonical fields. |
| GTN-8 | Offline prod gateways resolved              | `connect-webmethods-prod` and `vps-wm-link-prod` are repaired, archived, or explicitly marked replaced.     |

## 9. Non-Goals

- No service-mesh injector/controller in this normalization ticket.
- No blind DB-only rewrite without desired-state backing.
- No breaking rename of existing `GatewayInstance` IDs referenced by deployments.
- No requirement that all `STOA Link` entries become real sidecars; most may be
  correctly classified as `connect`.

## 10. Open Decisions

| Decision                  | Options                                             | Default                                                                    |
| ------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------- |
| Endpoint storage          | Structured JSON column vs normalized endpoint table | Structured JSON first if compatible with current API.                      |
| Prod edge identity        | One logical gateway vs two independent runtimes     | One logical gateway if health/version/runtime evidence matches.            |
| Offline webMethods prod   | Repair vs archive duplicate                         | Repair `connect-webmethods-prod`; archive `vps-wm-link-prod` if duplicate. |
| Sidecar proof persistence | Store proof snapshots in CP vs only compute live    | Store last proof snapshot for Console and auditability.                    |
