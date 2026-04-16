---
task_id: T-001
mega_id: CAB-1917
title: Phase 1 — Make API creation work end-to-end
owner: "@PotoMitan"
state: pending
blocked_by: []
pr: null
created_at: 2026-04-16
completed_at: null
---
# Phase 1 — Make API creation work end-to-end

## Goal

Fix the five bugs that currently prevent Backend API creation and
promotion from reaching a deployed state. Covers Phase 1 ACs of
`requirement.md`.

Council adjustment: each sub-item is a separate PR (micro-PR strategy).
This task file tracks the five PRs as one logical phase.

## Approach

Sub-PRs in dependency order:

1. **RegisterApiModal submit button** — FIRST COMMIT.
   - Files: `control-plane-ui/src/.../RegisterApiModal.tsx`.
   - Move submit button inside the `<form>` element; add vitest.
   - ~10 LOC.
2. **Deprecate legacy `POST /deployments`** with `Deprecation` +
   `Sunset` headers.
   - Files: `control-plane-api/.../routers/deployments.py`.
   - Contract test first (red), then header.
   - ~30 LOC.
3. **Wire `auto_deploy_on_promotion()` to promotion approval**.
   - Files: `control-plane-api/.../services/promotion_service.py`.
   - Regression test: approve promotion → GatewayDeployment row.
   - ~20 LOC.
4. **OpenAPI spec validation on API create** — reject invalid spec
   with `422` + structured error.
   - Files: `control-plane-api/.../routers/apis.py`.
   - Use existing `openapi-spec-validator`; add to requirements if
     missing.
   - ~50 LOC.
5. **Fix `list_apis` error swallowing** — propagate `503` from GitLab
   connector.
   - Files: `control-plane-api/.../services/gitops_api_service.py`.
   - Unit test with `httpx.MockTransport`.
   - ~10 LOC.

Commands to run before each PR:

- `cd control-plane-api && uv run pytest -q && uv run mypy .`
- `cd control-plane-ui && npm test -- --run && npm run lint`

## Done when

- [ ] All five PRs merged to `main` via squash, each referenced above.
- [ ] CI green on every PR (no pre-existing flakes attributed).
- [ ] Regression test committed for each `fix()` commit.
- [ ] Post-merge `/deploy-check` green.

## Notes

- RegisterApiModal is the P0 user-visible bug — ship it first on its
  own tiny PR so it can backport-merge without waiting on the phase.
- Contract test for (2) is mandatory before shipping the deprecation
  header; it is the regression guard once the endpoint is removed.
