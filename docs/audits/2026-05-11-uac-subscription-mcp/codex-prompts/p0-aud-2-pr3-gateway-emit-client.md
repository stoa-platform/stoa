# Codex prompt — P0-AUD-2 PR 3 (Gateway: emit client + readiness + wiring)

You are implementing **PR 3 of P0-AUD-2** in the STOA monorepo
(`/Users/torpedo/hlfh-repos/stoa`), component `stoa-gateway/` (Rust, Tokio).

Read `p0-aud-2-README.md` and ADR-070 §4.6. Follow the conventions from
`p0-mcp-1-pr2-gateway.md`.

## Branch base — IMPORTANT

This PR has a **hard code dependency on PR 2** (`stoa-gateway/src/audit/spool.rs`
— it *uses* the spool, cannot mock it). PR 2 landed as **PR #2792**. Do **not**
branch off plain `origin/main` until #2792 is merged — the `audit::spool`
module would be absent and the crate would not compile. Branch base:
- **Preferred:** dispatch this PR only *after* #2792 merges to `main`; then
  branch off fresh `origin/main`.
- If dispatched earlier: branch off #2792's branch
  `feat/cab-2227-aud-2-gateway-audit-spool` (stacked PR — flag it as stacked in
  the PR description; rebase onto `main` once #2792 merges).

PR 1 (CP-API audit emit) landed as **PR #2793**; this PR depends only on its
HTTP contract below, no code dependency (cross-language).

## Frozen upstream contract

**From PR #2793 — `/v1/internal/audit/emit`:**
- `POST {cp_url}/v1/internal/audit/emit`
- Headers: `Authorization: HMAC-SHA256 <hex>`, `X-Timestamp: <unix>`,
  `Idempotency-Key: <uuid>` (all required).
- **HMAC signing string** (reproduce byte-for-byte):
  `f"{timestamp}\n{method}\n{path}\n{sha256_hex(body)}"`, HMAC-SHA256 keyed by
  the shared secret (`INTERNAL_AUDIT_HMAC_SECRET` on the CP side; Vault-sourced
  on the gateway side). Replay window 300 s.
- Request body: the 15-field schema — `source` ("stoa-gateway"), `event_type`,
  `decision` ("allow"|"deny"), `reason`, `tenant_id`, `actor_id`|null,
  `session_id`|null, `resource_type`, `resource_id`, `tool_call_id`,
  `approval_id`|null, `policy_version`|null, `correlation_id`, `occurred_at`
  (ISO-8601 UTC), `details` (object). Extra fields are rejected — send exactly
  these. Success = `202`; duplicate `Idempotency-Key` also `202`.

**From PR #2792 — `audit::spool` (confirm exact signatures in
`stoa-gateway/src/audit/`):** `AuditSpool::open(dir, config)`,
`append(&self, AuditEvent) -> Result<(), SpoolError>`,
`drain_oldest(&self, max) -> Vec<(cursor, AuditEvent)>`, `ack(&self, cursor)`,
`depth()`, `oldest_age()`, `is_over_high_water() -> bool`; the sole error
variant `SpoolError::GapDeclared(String)`; `AuditEvent` in `audit/event.rs`
(carries an `idempotency_key`). The wire shape of `AuditEvent` already matches
PR #2793's request schema (PR 2's `regression_audit_event_wire_shape_matches_cp_schema`
asserts it).

## Goal

Wire the spool to CP-API: a background flusher that ships in-scope audit
events HMAC-signed and idempotently, with the ADR-070 §4.6 readiness coupling,
no-silent-drop incident path, replay-on-recovery, and operator metrics — and
enqueue the gateway's deny / approval-gated decisions into the spool.

## Branch / ticket

`feat/cab-2227-aud-2-gateway-audit-emit-client` off fresh `origin/main`. First
commit subject carries `CAB-2227`. Scope `gateway`.

## Scope

### 1. Emit client — `stoa-gateway/src/audit/client.rs`

- `AuditEmitClient` — `POST {cp_url}/v1/internal/audit/emit` with the HMAC
  auth from PR 1 (`Authorization: HMAC-SHA256 <hex>`, `X-Timestamp`,
  `Idempotency-Key` = the event's `idempotency_key`). Signing string MUST match
  PR 1 byte-for-byte. Shared secret from config, Vault-sourced.
- Treats `202` as success; any other status or transport error → retryable.

### 2. Background flusher — `audit/flusher.rs`

A Tokio task started from `AppState::start_background_tasks`:

- Loop: `spool.drain_oldest(batch)` → emit each via the client → `spool.ack` on
  `202`. Retry with exponential backoff on failure; never `ack` an unconfirmed
  event.
- **Replay on recovery** (§4.6.4): drains oldest-first preserving
  `correlation_id` / ADR-068 chain order. After a backlog drains following a CP
  outage, emit a `audit_chain_resumed` log + metric with the count and time
  window covered.
- **No silent drop** (§4.6.3): if `spool.append` ever returns
  `SpoolError::GapDeclared`, emit a synchronous `audit_gap_declared` event
  (local log + stderr + the gateway's fail-closed flag) and flip the gateway
  to fail-closed/deny-by-default for in-scope decisions. A declared gap is an
  incident.

### 3. Readiness coupling — `lib.rs::ready` + `health.rs`

ADR-070 §4.6.2: when `spool.is_over_high_water()` is true, `/ready` (and
`/health/ready`) returns `503` — the orchestrator stops routing new traffic
until the spool drains. **Liveness (`/health`, `/health/live`) is unaffected.**
Extend the existing `policy_ready()`-style readiness check (added in the GW-2
PR) with a spool-pressure term. Admin `/health` reports `degraded` likewise.

### 4. Metrics — `metrics.rs`

ADR-070 §4.6.5 + plan §6.1: register and update
- `gateway_audit_spool_depth`
- `gateway_audit_spool_oldest_age_seconds`
- `gateway_audit_gap_declared_total`
- `gateway_audit_emit_lag_seconds`
- `gateway_audit_emit_dropped_total` (stays 0 unless a gap is declared)

### 5. Wire the in-scope events

Enqueue an `AuditEvent` into the spool at the gateway's **deny** and
**approval-gated** decision points — at minimum the `tool_call_denied` path in
`control_plane/tool_permissions.rs` and the approval-gate decision in
`mcp/handlers.rs` (the gate from P0-MCP-1 PR 2 — if that PR has not merged yet,
wire only the `tool_permissions.rs` deny path and leave a clearly-marked
`// P0-MCP-1 follow-up` hook at the approval site). Phase 0 scope is **denies +
approval-gated only** — do not enqueue successful ordinary calls.

## Tests — `fn regression_*` + `// regression for CAB-2227`, test-first

Use `wiremock` for the CP `/v1/internal/audit/emit` endpoint; `tempdir` spool.

- `regression_audit_flusher_ships_deny_event_to_cp` — deny enqueued → wiremock
  receives a correctly HMAC-signed 202-acked request.
- `regression_audit_flusher_retries_until_cp_acks` — CP 503 then 202 → event
  delivered exactly once, acked only after 202.
- `regression_audit_flusher_replays_backlog_oldest_first_after_outage`.
- `regression_readiness_fails_when_spool_over_high_water` — `/ready` → 503.
- `regression_liveness_unaffected_by_spool_pressure` — `/health` still 200.
- `regression_gap_declared_flips_gateway_fail_closed`.
- `regression_tool_call_deny_is_enqueued_to_audit_spool`.

## Constraints

- **PR ≤ 300 LOC**; if exceeded split (client+flusher / readiness+metrics+wiring).
- `cargo fmt --check`, `clippy --all-targets -D warnings`, `cargo test` clean —
  show the output line for every `regression_*` test.
- Do not regress the GW-2 readiness behaviour; extend it.
- gateway coverage gate — do not lower it.

## Deliverable

Draft PR to `main`, body `Linear: [CAB-2227]`. Report the final insertion count
and confirm the HMAC signing string matches PR 1. Note in the PR description
whether the `mcp/handlers.rs` approval-site wiring was done or left as a
P0-MCP-1 follow-up hook.

## Phase 0 close

With PR 3 merged + deployed, **P0-AUD-2 is complete and Phase 0 of the
corrective plan closes** (challenger C1 Option A satisfied). Run `/verify-mega`
discipline on the Phase 0 set before declaring closure.
