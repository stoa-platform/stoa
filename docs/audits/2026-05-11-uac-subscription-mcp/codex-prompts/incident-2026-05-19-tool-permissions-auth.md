# Codex prompt — Option 1: authenticated gateway → CP tool-permissions path

Follow-up to the **2026-05-19 gateway outage** (CAB-2227). Repo `stoa`
(`/Users/torpedo/hlfh-repos/stoa`).

## Background — the incident

The Rust gateway's `ToolPermissionService` (`stoa-gateway/src/control_plane/
tool_permissions.rs`) fetches tenant tool-permissions from CP-API
`GET /v1/tenants/{tenant_id}/tool-permissions`. That endpoint
(`control-plane-api/src/routers/tenant_tool_permissions.py`, `list_permissions`)
is guarded by `Depends(get_current_user)` — it requires a **user JWT**. The
gateway holds **no** credential for it (`ToolPermissionService::new` never
receives one), so the call has **always returned 401**. The old permissive
code masked it; #2787's fail-closed turned it fatal.

**Hotfix already shipped (Option 2, PR #2796):** `/ready` no longer gates on
tool-permission availability. But the data-plane fetch still 401s, so
`is_tool_allowed` always denies (or, deny-by-default, never has a real allow
set) — **tool-permission enforcement is still non-functional**. Option 1 fixes
the data path.

## Goal

Give the gateway an **authenticated** path to tenant tool-permissions so the
fetch returns real data, restoring genuine deny/allow enforcement.

## Scope — 2 small PRs, cp-api first

### PR 1 — CP-API internal endpoint

`control-plane-api/`, scope `api`, branch `feat/cab-2227-internal-tool-permissions`.

- New route **`GET /v1/internal/tenants/{tenant_id}/tool-permissions`**
  (add to `tenant_tool_permissions.py` or a small internal router).
- Auth: **`X-Gateway-Key`** via `_validate_gateway_key` (reuse from
  `src/routers/gateway_internal.py`) — **not** `get_current_user`.
- Response body: **identical shape** to the existing `list_permissions`
  (`{"items":[{"mcp_server_id","tool_name","allowed"}],"total",...}`) — the
  gateway's `PermissionListResponse`/`PermissionItem` already parse this; do
  not change the shape. Reuse the same query/`_load_permission_cache` logic.
- Tests (`test_regression_cab_2227_*`, real test DB): valid gateway key → 200 +
  correct items; missing/invalid key → 401; unknown tenant → empty list or 404
  consistent with the gateway's 404-handling (`fetch_permissions` treats 404 as
  `PermissionAbsent`).

### PR 2 — Gateway auth wiring

`stoa-gateway/`, scope `gateway`, branch `fix/cab-2227-tool-permissions-auth`.

- `ToolPermissionService` gains a gateway key. `new(...)` takes
  `gateway_key: Option<String>` (or a dedicated `with_gateway_key`).
- `fetch_permissions`: call **`/v1/internal/tenants/{tenant_id}/tool-permissions`**
  and send the `X-Gateway-Key` header when the key is set.
- `state.rs` (~line 573): pass `config.control_plane_api_key` into
  `ToolPermissionService::new` (the same key already used for `/v1/internal/*`
  tool discovery — see `state.rs:217-219`).
- **Tests — cover the auth-failure path, not only 200.** The original tests
  mocked CP with wiremock returning **only 200**, which is exactly why the prod
  401 was never caught. Add wiremock cases asserting: 200 + key → parsed allow
  set; **401/403 → `CpUnreachable` deny**; and that the request actually
  carries the `X-Gateway-Key` header (wiremock header matcher).

## Out of scope — do NOT re-couple `/ready`

PR #2796 deliberately decoupled tool-permission availability from pod
readiness. **Leave it decoupled.** Whether to ever re-couple is an ADR-070
posture decision for the operator/Council — not part of this fix.

## Conventions

Branch/commit/test-first/≤300-LOC/validation conventions as in the sibling
`p0-mcp-1-pr1-cp-api.md` / `p0-mcp-1-pr2-gateway.md`. Rust regression tests
named `fn regression_*`. First commit subject carries `CAB-2227`.
