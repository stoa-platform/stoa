---
title: "Release: Promotion Deploy Chain (2026-03-27)"
---

# Release: Promotion Deploy Chain

**Date:** 2026-03-27
**Components:** Control Plane API, STOA Connect (Go)
**Migration required:** Yes (Alembic 081)
**ADR:** [ADR-059: Promotion Deploy Chain](../architecture/adr-059-promotion-deploy-chain.md)

## Summary

Closed-loop promotion deployment: promotions now track deployment status end-to-end and automatically transition to `promoted` or `failed` based on gateway sync results. Previously, promotions for agent-managed gateways (STOA Connect) remained stuck in `promoting` indefinitely.

## Changes

### Control Plane API (Python)

- **State machine guard** — `complete_promotion()` and `fail_promotion()` reject non-`promoting` status with `ValueError` (idempotent on re-entry)
- **Route sync-ack endpoint** — `POST /v1/internal/gateways/{gateway_id}/route-sync-ack` accepts deployment results from STOA Connect agents. Two-pass processing: updates deployment statuses, then checks promotion completion for each linked promotion
- **FK `promotion_id`** — `GatewayDeployment` now links to the triggering promotion via nullable FK (migration 081, `ondelete="SET NULL"`, indexed via `ix_gw_deploy_promotion`)
- **Auto-completion** — `check_promotion_completion()` queries all deployments by `promotion_id`. All `synced` -> `promoted`. Any `error` with no `pending`/`syncing` remaining -> `failed` with reason `"Partial deployment failure: N/M gateways failed"`
- **Enriched routes** — `GET /v1/internal/gateways/routes` now includes `deployment_id` in each route item
- **Kafka consumer** — `PromotionDeployConsumer` (group `promotion-deploy-consumer`) handles `promotion-approved` events from `stoa.deploy.requests` topic, calling `auto_deploy_on_promotion()` to create deployments linked to the promotion

### STOA Connect (Go)

- **Route sync-ack reporting** — After `SyncRoutes()`, builds `[]SyncedRouteResult` from routes (skipping empty `DeploymentID`) and calls `ReportRouteSyncAck()` fire-and-forget
- **Post-deploy verification** — webMethods adapter calls `GET /rest/apigateway/apis/{id}` after create/update to verify `isActive`. If `false`, calls `PUT /rest/apigateway/apis/{id}/activate` as fallback
- **New types** — `SyncedRouteResult{DeploymentID, Status, Error}`, `RouteSyncAckPayload{SyncedRoutes, SyncTimestamp}`
- **Route struct enriched** — `DeploymentID` field added to `adapters.Route`

## Migration

```bash
alembic upgrade head  # applies migration 081_add_promotion_id_to_gateway_deployments
```

Migration 081 adds:
- Column `promotion_id` (UUID, nullable, FK to `promotions.id`, SET NULL on delete)
- Index `ix_gw_deploy_promotion` on `gateway_deployments.promotion_id`

Down revision: `080_add_policy_sync_status`

## Breaking Changes

None. All changes are backward compatible:

- `promotion_id` is nullable — existing deployments are unaffected
- `deployment_id` in routes defaults to empty string — existing STOA Connect agents skip ack for empty IDs
- `route-sync-ack` is a new endpoint — no existing consumer calls it
- `check_promotion_completion` is a no-op when no deployments are linked to a promotion

## Test Coverage

### Python — Control Plane API

| Area | File | Tests |
|------|------|-------|
| Route sync-ack basics | `test_gateway_internal.py::TestRouteSyncAck` | 4 (success, failed, mixed, not found) |
| Promotion completion | `test_gateway_internal.py::TestRouteSyncAckPromotionCompletion` | 5 (complete, partial, all synced, error, mixed) |
| Integration chain | `test_integration_promotion_chain.py::TestPromotionChainIntegration` | 5 (happy single/multi-gw, partial failure, state guard, idempotence) |

### Go — STOA Connect

| Area | File | Tests |
|------|------|-------|
| Route sync | `webmethods_test.go` | 3 (sync, idempotent, spec hash skip) |
| Verify + activate | `webmethods_test.go` | 3 (verify after create, activate if not active, fail if activate fails) |
| Deactivation | `webmethods_test.go` | 2 (activate/deactivate, sync with deactivation) |
| OpenAPI downgrade | `webmethods_test.go` | 1 (3.1 to 3.0.3) |

## Related Documentation

- [ADR-059: Promotion Deploy Chain](../architecture/adr-059-promotion-deploy-chain.md)
- [Promotion Flow End-to-End Guide](../guides/promotion-flow-e2e.md)
