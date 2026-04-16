---
task_id: T-002
mega_id: CAB-1917
title: Phase 2 — Deployment reliability
owner: "@PotoMitan"
state: pending
blocked_by: [T-001]
pr: null
created_at: 2026-04-16
completed_at: null
---
# Phase 2 — Deployment reliability

## Goal

Stabilise `GatewayDeploymentService` + `SyncEngine` so that every
promotion approved in Phase 1 lands on the target gateway with the
correct policy and is observable. Covers Phase 2 ACs of
`requirement.md`.

## Approach

Ordered sub-PRs:

1. **Canonical policy config schema doc** — prerequisite for
   normalisation.
   - File: `control-plane-api/docs/policy-config-schema.md`.
   - Owner of the source of truth for 7 adapters.
2. **`build_desired_state()` emits HTTP methods** per API.
   - Files: `control-plane-api/.../services/desired_state.py`.
   - ~30 LOC.
3. **Normalise policy config keys across 7 adapters** —
   table-driven test.
   - Files: `control-plane-api/.../adapters/{kong,gravitee,webmethods,...}_adapter.py`.
   - ~50 LOC.
4. **Atomic GitLab delete** — one commit with all deletions.
   - Files: `control-plane-api/.../connectors/gitlab_connector.py`.
   - Integration test covers rollback.
   - ~20 LOC.
5. **Track `policy_sync_status` on `GatewayDeployment`**.
   - Files: Alembic migration + model + service writes.
   - Migration COMMIT before `ADD VALUE` (local gotcha per MEMORY).
   - ~40 LOC.
6. **Drift detection handles empty `spec_hash`**.
   - Files: `control-plane-api/.../services/drift_service.py`.
   - Unit test asserts drift reported.
   - ~20 LOC.
7. **SyncEngine retry counter on inline failure**.
   - Files: `control-plane-api/.../services/sync_engine.py`.
   - Unit test.
   - ~5 LOC.

## Done when

- [ ] All seven sub-items merged; each references a PR above.
- [ ] `GET /v1/gateway/deployments/{id}` response includes
      `policy_sync_status`.
- [ ] Adapter conformance test is green for all 7 adapters.
- [ ] Post-merge `/deploy-check` green.

## Notes

- Phase 2 blocked by T-001 because Phase 1 wires the canonical
  deployment path; Phase 2 hardens it. Merging Phase 2 without Phase 1
  would touch dead code.
- Alembic migration gotcha (MEMORY): `COMMIT` between
  `CREATE TYPE` and `ADD VALUE`. Tilt local verifies this.
