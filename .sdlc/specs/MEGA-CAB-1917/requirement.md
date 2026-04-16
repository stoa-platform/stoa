---
mega_id: CAB-1917
title: Fix API creation and deployment pipeline end-to-end
owner: "@PotoMitan"
state: council-validated
impact_level: HIGH
council_score: 8.25       # S1, 2026-03-26
adrs: []
created_at: 2026-04-16
shipped_at: null
---
# Fix API creation and deployment pipeline end-to-end

## Problem

Deep audit of the STOA API creation and deployment flow found the core
pipeline broken in multiple places:

- Two parallel, disconnected API models (GitOps APIs + Backend APIs) that
  were never unified.
- Two parallel deployment tracking systems (legacy `deployments` table
  vs. modern `gateway_deployments` table).
- The legacy deployment endpoint publishes to a Kafka topic with no
  consumer (dead end).
- `RegisterApiModal` submit button is rendered outside the `<form>`
  element, so it is non-functional — users cannot register a Backend API
  at all.
- `auto_deploy_on_promotion()` is dead code; promotion approvals never
  trigger deployments.
- Policy enforcement on the proxy path is soft-mode only.

Canonical architecture decision taken during Council:
`DeploymentOrchestrationService` → `GatewayDeploymentService` →
`SyncEngine` is THE canonical deployment path. The legacy `Deployment`
table and `deploy-requests` Kafka topic are deprecated.

## Out of scope

- UAC classification graduation (soft → hard mode) — separate ticket.
- Unifying GitOps APIs and Backend APIs into a single model.
- E2E Playwright tests for the OAuth flow.
- `datetime.utcnow()` replacement — mechanical chore, separate ticket.
- Dead code cleanup for `ToolRegistry` and `handlers/health.rs`.

## Architecture touchpoints

Impact verified via `stoa-impact` MCP (see `.sdlc/context/architecture.md`).

- `control-plane-api` — API + promotion endpoints, OpenAPI validation,
  orchestration service, legacy deprecation.
- `control-plane-ui` — `RegisterApiModal` fix, Backend API
  detail/edit view, gateway admin input validation, deploy dialog.
- `portal` — catalog error handling.
- `stoa-gateway` — consumers of policy config keys (read-only;
  normalization happens server-side).
- Adapters (7) — Kong, Gravitee, webMethods, Azure APIM, Apigee, AWS
  API Gateway, WSO2 — policy config key normalization.

## Acceptance criteria (binary DoD)

Phase 1 — API creation works end-to-end:

- [ ] `RegisterApiModal` submit button triggers form submission; vitest
      unit test + manual Playwright scenario cover it.
- [ ] Legacy `POST /deployments` returns `Deprecation` + `Sunset`
      response headers; contract test asserts header presence.
- [ ] `auto_deploy_on_promotion()` is wired to promotion approval; a
      promotion approval produces a `GatewayDeployment` row.
- [ ] Invalid OpenAPI spec on API create returns `422` with a
      structured error, not `500`.
- [ ] `list_apis` returns `503` on GitLab connector errors (not an
      empty list).

Phase 2 — deployment reliability:

- [ ] Canonical policy config schema committed to
      `control-plane-api/docs/policy-config-schema.md`.
- [ ] `build_desired_state()` emits HTTP methods per API; assertion in
      existing desired-state test.
- [ ] Policy config keys identical across all 7 adapters; one
      table-driven test covers all.
- [ ] GitLab delete is a single commit (atomic); integration test
      covers rollback on failure.
- [ ] `GatewayDeployment.policy_sync_status` column populated on every
      sync; DB migration shipped.
- [ ] Drift detector reports drift when `spec_hash` is empty (today it
      silently skips).
- [ ] `SyncEngine` retry counter increments on inline sync failure; unit
      test asserts counter value.

Phase 3 — UI completeness:

- [ ] Console shows Backend API detail + edit view (`/apis/backend/:id`).
- [ ] Portal catalog page shows an error state on fetch failure (not a
      blank grid).
- [ ] Gateway admin rejects `backend_url` failing SSRF pre-check
      (private IP ranges, `localhost`, link-local) with `400`.
- [ ] Deploy API dialog supports search by name/tag.

Cross-cutting:

- [ ] Each phase ships as separate PRs. No PR > 300 LOC.
- [ ] Every `fix()` commit has a regression test that fails before the
      fix and passes after.
- [ ] `/deploy-check` green after each phase merges.

## Tasks

See `tasks/`. Order is `T-001` → `T-002` → `T-003`. Within each task,
sub-items follow the Linear ticket's phase order.

## References

- Linear: https://linear.app/hlfh-workspace/issue/CAB-1917
- Council decision: inline in Linear description (S1, 8.25/10, 2026-03-26)
- Related MEGA: CAB-1977 (observability) — independent, same project
