# Spec: Catalog Gateway DR Reconciliation

> Status: implemented in `control-plane-api` on 2026-05-01.
> Related docs: `specs/api-creation-gitops-rewrite.md`, ADR-035 Gateway Adapter Pattern, ADR-057 `stoa-connect`.

## Problem

`stoa-catalog` can reconstruct `api_catalog`, but a platform rebuild must also recover the runtime deployment queue. Before this spec, the Git catalog projection preserved `target_gateways` and `openapi_spec`, but did not recreate `GatewayDeployment` rows from Git. A rebuilt Control Plane could therefore know that an API exists without knowing which gateway should receive it.

## Goal

When catalog sync or the in-tree catalog reconciler reads an API definition from Git, explicit gateway targets in `api.yaml` are materialized into `GatewayDeployment` rows with `sync_status=PENDING`. The existing gateway sync engine and `stoa-connect` then converge the data plane through the normal Control Plane path.

## Contract

The source of truth is the API definition file in `stoa-catalog`:

```yaml
gateways:
  - instance: connect-webmethods-dev
    environment: dev
    activated: true
```

or:

```yaml
deployments:
  dev:
    gateways:
      - instance: connect-webmethods-dev
        activated: true
```

Supported target shapes:

| Shape | Meaning |
|---|---|
| `gateways: [{instance, environment?, activated?}]` | Explicit gateway targets |
| `gateways: [gateway-name]` | Explicit gateway target names |
| `gateways: {gateway-name: {activated: true}}` | Explicit name map |
| `deployments.<env>.gateways` | Explicit gateway targets scoped to an environment |
| `deployments.<env>.gateway` | Single explicit gateway target scoped to an environment |
| `deployments.<env>: true` | Environment marker only; not materializable without a gateway instance |

`spec.gateway` in Kubernetes-style catalog entries describes webMethods API settings and is not interpreted as a STOA gateway deployment target.

## Acceptance Criteria

- [x] AC1: GitHub and GitLab catalog providers normalize Kubernetes-style and flat API definitions through the same helper.
- [x] AC2: `api_catalog.target_gateways` is populated only from explicit gateway target declarations.
- [x] AC3: Manual catalog sync creates a `GatewayDeployment(PENDING)` for each explicit target gateway.
- [x] AC4: The in-tree catalog reconciler also creates/updates `GatewayDeployment` rows on absent rows, projection drift, and healthy rows whose deployment targets drifted.
- [x] AC5: Existing deployments are reset to `PENDING` only when the computed desired state changes.
- [x] AC6: A target gateway can resolve by registered name or by self-registered hostname/instance id.
- [x] AC7: Environment-only deployment markers log a warning and do not guess a gateway.
- [x] AC8: Data-plane rebuild still goes through the Control Plane; the data plane does not pull Git directly.

## ADR Compliance

This keeps ADR-035 intact: the Control Plane remains the orchestrator, `GatewayDeployment` is the desired-state queue, and gateway adapters/agents perform runtime application. It also keeps ADR-057 intact: `stoa-connect` synchronizes routes from the Control Plane and acknowledges results back to it.

The data plane deliberately does not rebuild itself from Git. Letting every gateway read `stoa-catalog` directly would duplicate auth, tenancy, promotion, policy, and audit decisions outside the Control Plane.

## UAC Applicability

No new UAC contract is introduced here. This spec changes an internal reconciliation path behind existing admin catalog sync behavior; it is not an MCP-exposed or agent-facing API operation.

If STOA later exposes "resync catalog/gateways" as an agent tool, that operation must get a UAC contract with `endpoint.llm` metadata before it is projected to MCP:

- `side_effects: "write"`
- `safe_for_agents: false`
- `requires_human_approval: true`

## Out of Scope

- Soft-delete/prune when a gateway target is removed from Git.
- Direct Git pull from the data plane.
- Guessing gateway targets from `deployments.dev: true`.
- Migrating existing catalog entries to add explicit gateway targets.
- Changing promotion approval semantics or the public deployment APIs.
