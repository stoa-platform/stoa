---
task_id: T-003
mega_id: CAB-1917
title: Phase 3 — UI completeness
owner: "@PotoMitan"
state: pending
blocked_by: [T-002]
pr: null
created_at: 2026-04-16
completed_at: null
---
# Phase 3 — UI completeness

## Goal

Close the UX gaps around the now-functional pipeline: Backend API
detail/edit view, Portal catalog error handling, Gateway admin input
validation with SSRF pre-check, Deploy dialog search. Covers Phase 3
ACs of `requirement.md`.

## Approach

Ordered sub-PRs:

1. **Backend API detail + edit view** — new Console page.
   - Files: `control-plane-ui/src/pages/apis/BackendApiDetail.tsx` +
     routing, form, vitest.
   - ~200 LOC — the largest sub-PR of the MEGA. Stay under 300 LOC by
     deferring bulk-edit to a follow-up if needed.
2. **Portal catalog error state** — replace blank grid with error UI
   on fetch failure.
   - Files: `portal/src/.../CatalogPage.tsx`.
   - MSW test for fetch failure path.
   - ~30 LOC.
3. **Gateway admin SSRF pre-check** — reject private IP ranges,
   `localhost`, link-local in `backend_url`.
   - Files: `control-plane-api/.../schemas/gateway_admin.py` +
     validator.
   - Use `ipaddress` module; cover IPv4 + IPv6.
   - Unit tests for each rejected class.
   - ~40 LOC.
4. **Deploy API dialog search** — filter list by name/tag.
   - Files: `control-plane-ui/src/.../DeployApiDialog.tsx`.
   - Client-side filter; no new API endpoint.
   - ~20 LOC.

## Done when

- [ ] All four sub-items merged; each references a PR above.
- [ ] Playwright smoke: log in as tenant-admin, register Backend API,
      edit it, see it in Deploy dialog via search → evidence archived
      in `docs/audits/2026-04-<dd>-cab-1917/`.
- [ ] Post-merge `/deploy-check` green.
- [ ] MEGA DoD checklist in `requirement.md` fully checked.

## Notes

- (3) is a security fix — MUST land with a regression test even though
  it lives in Phase 3. SSRF pre-check predates this MEGA but was never
  wired on the admin path.
- After this task's PRs merge, run `/verify-mega CAB-1917` to close
  out. Do not mark Linear Done manually.
