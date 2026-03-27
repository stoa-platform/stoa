---
title: "ADR-059: Promotion Deploy Chain — Closed Loop Architecture"
status: accepted
date: 2026-03-27
deciders: Christophe (CAB Ingenierie)
---

# ADR-059: Promotion Deploy Chain — Closed Loop Architecture

## Context

The promotion workflow allowed approving a promotion and triggering deployment, but the feedback loop was never closed. When a promotion was approved, the Control Plane created `GatewayDeployment` records and attempted inline sync via gateway adapters. However, for agent-managed gateways (STOA Connect), the CP cannot push directly — the agent polls the CP. The result: promotion status remained `promoting` indefinitely because the CP had no mechanism to receive deployment confirmation from STOA Connect agents.

Additionally, there was no direct link between a promotion and its resulting deployments. The only way to correlate them was through `api_id` + `target_environment`, which is ambiguous when multiple deployments exist for the same API on different gateway instances.

## Decision

### 1. Pull model for STOA Connect

STOA Connect polls the Control Plane every 30 seconds via `GET /v1/internal/gateways/routes`. The CP never initiates a connection toward the agent.

**Rationale:** On-premise security constraints prohibit inbound connections. The agent lives behind firewalls with no open ports. Pull is the only viable model.

### 2. Route sync-ack endpoint (new)

`POST /v1/internal/gateways/{gateway_id}/route-sync-ack` — the agent reports deployment results per route. This is separate from the existing policy `sync-ack` endpoint (`POST /v1/internal/gateways/{gateway_id}/sync-ack`).

**Rationale:** Routes and policies have different contracts and lifecycles. Route ack carries `deployment_id` + `status` (applied/failed). Policy ack carries `policy_id` + `status` (applied/failed/removed). Mixing them would create coupling between unrelated concerns.

**Request schema:**

```json
{
  "synced_routes": [
    {
      "deployment_id": "uuid",
      "status": "applied|failed",
      "error": "optional error message"
    }
  ],
  "sync_timestamp": "2026-03-27T12:00:00Z"
}
```

### 3. Ack global per batch (not per route)

The `GatewayAdapter.SyncRoutes()` interface returns a single error for the entire batch. On the ack side, all routes in the batch receive the same status: either all `applied` or all `failed`.

**Rationale:** Simplicity. The 3 adapter implementations (webMethods, Kong, Gravitee) would each need per-route error tracking to support granular acks. The current interface (`SyncRoutes(ctx, adminURL, routes) error`) does not expose per-route results. Per-route ack is a future evolution when adapters support it.

### 4. FK promotion_id on GatewayDeployment

Added a nullable `promotion_id` foreign key on `gateway_deployments` (migration 081). On delete: `SET NULL`. Indexed via `ix_gw_deploy_promotion`.

**Rationale:** The indirect link through `api_id` + `target_environment` is ambiguous when multiple deployments exist for the same API across different gateway instances. A direct FK allows `check_promotion_completion()` to query all deployments linked to a specific promotion in a single query via `list_by_promotion(promotion_id)`.

### 5. Verify + Activate fallback on webMethods

After `PUT /rest/apigateway/apis/{id}` or `POST /rest/apigateway/apis`, the webMethods adapter calls `GET /rest/apigateway/apis/{id}` to verify `isActive`. If `false`, it explicitly calls `PUT /rest/apigateway/apis/{id}/activate`.

**Rationale:** webMethods does not guarantee activation via the `"isActive": true` field in the create/update body. The flag is sometimes ignored silently. Kong and Gravitee do not have this issue. Tests: `TestWebMethodsSyncRoutesVerifiesActiveAfterCreate`, `TestWebMethodsSyncRoutesActivatesIfNotActive`, `TestWebMethodsSyncRoutesFailsIfActivateFails`.

## Consequences

### Positive

- **Closed loop:** promote -> deploy -> verify -> ack -> PROMOTED (or FAILED)
- **Real-time status:** Console reflects actual deployment state, not just intent
- **Partial failure detection:** `check_promotion_completion()` transitions to FAILED when at least one deployment is ERROR and no PENDING/SYNCING remain
- **Idempotent:** State machine guards in `complete_promotion()` and `fail_promotion()` catch `ValueError` silently (already transitioned). `route-sync-ack` processes each result independently
- **Backward compatible:** `promotion_id` is nullable (existing deployments unaffected). `deployment_id` in routes defaults to empty string. `route-sync-ack` is a new endpoint (no existing consumers)

### Negative

- **Latency ~30s:** Poll interval of STOA Connect means promotion completion is delayed by up to 30 seconds after the gateway actually applies routes
- **Ack granularity:** If one route fails on webMethods, all routes in the batch are marked failed (global error from `SyncRoutes()`)
- **Migration required:** Alembic migration 081 must be applied before the feature works

### Risks

- **Race condition on multi-gateway:** Two gateways acking concurrently for the same promotion. Mitigated by idempotent state machine guards (`ValueError` catch in `complete_promotion` / `fail_promotion`)
- **webMethods response parsing:** If the POST/PUT response body cannot be parsed, the adapter degrades to fire-and-forget (ack still sent as `applied` based on HTTP 200/201 status)

## Related

- Migration: `081_add_promotion_id_to_gateway_deployments` (revision `081_add_promotion_id_to_gw_deploy`, down `080_add_policy_sync_status`)
- Endpoint: `POST /v1/internal/gateways/{gateway_id}/route-sync-ack` (gateway_internal.py:554-637)
- Consumer: `PromotionDeployConsumer` (Kafka group `promotion-deploy-consumer`, topic `stoa.deploy.requests`)
- Completion logic: `PromotionService.check_promotion_completion()` (promotion_service.py:207-242)
- Technical guide: [Promotion Flow End-to-End](../guides/promotion-flow-e2e.md)
