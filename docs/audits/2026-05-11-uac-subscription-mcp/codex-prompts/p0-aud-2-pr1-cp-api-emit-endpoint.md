# Codex prompt — P0-AUD-2 PR 1 (CP-API: `/v1/internal/audit/emit`)

You are implementing **PR 1 of P0-AUD-2** in the STOA monorepo
(`/Users/torpedo/hlfh-repos/stoa`), component `control-plane-api/` (Python 3.11,
FastAPI, SQLAlchemy async).

Read first: the sibling `p0-aud-2-README.md` (spec source, scope boundary, the
HMAC auth decision), `adrs-drafts/adr-070-gateway-fail-closed-posture.md` §4.6,
`adrs-drafts/adr-068-audit-log-actor-resource-doctrine.md` (the audit schema),
plan §6.1. **ADR-070 §4.6 is binding.** Follow the branch/commit/test
conventions from `p0-mcp-1-pr1-cp-api.md`.

## Goal

A CP-API inbound endpoint that the gateway calls to record in-scope audit
decisions (denies, approval-gated) into the authoritative ADR-068 audit chain,
with tamper-evident inter-service auth and idempotent delivery.

## Branch / ticket

`feat/cab-2227-aud-2-cp-api-audit-emit` off fresh `origin/main`. First commit
subject carries `CAB-2227`. Conventional commits, scope `api`.

## Scope

### 1. Endpoint — `POST /v1/internal/audit/emit`

New router `control-plane-api/src/routers/audit_internal.py`, prefix
`/v1/internal`. Request body (ADR-068-aligned; reuse the plan §6.1 shape):

```json
{
  "source": "stoa-gateway",
  "event_type": "TOOL_CALL_DECISION",
  "decision": "allow|deny",
  "reason": "string",
  "tenant_id": "uuid",
  "actor_id": "uuid|null",
  "session_id": "string|null",
  "resource_type": "mcp_tool",
  "resource_id": "tool_name",
  "tool_call_id": "uuid",
  "approval_id": "uuid|null",
  "policy_version": "string|null",
  "correlation_id": "uuid",
  "occurred_at": "ISO8601 UTC",
  "details": {}
}
```

Validate with a Pydantic model. Map onto `AuditService.record_event` (see
`src/services/audit_service.py` — `action=event_type.lower()`,
`outcome="failure" if decision=="deny" else "success"`,
`resource_type`/`resource_id`/`correlation_id` direct, `actor_type="service"`,
`details` carrying `reason`, `tool_call_id`, `approval_id`, `policy_version`,
`source`). `occurred_at` → `created_at`. Returns `202 Accepted` on success.

### 2. Inter-service auth — HMAC-SHA256

Per ADR-070 §4.6, **not** the `X-Gateway-Key` static header used by other
`/v1/internal/*` routers. Implement an HMAC verifier (new
`src/auth/internal_hmac.py`, FastAPI dependency):

- Headers: `Authorization: HMAC-SHA256 <hex>`, `X-Timestamp: <unix>`.
- Signature = `HMAC-SHA256(shared_secret, f"{timestamp}\n{method}\n{path}\n{sha256(body)}")`.
- Reject: bad signature → 401; `|now - timestamp| > 300s` → 401 (replay window);
  missing headers → 401. Constant-time compare (`hmac.compare_digest`).
- `shared_secret` from settings, sourced from Vault — `REPLACE_FROM_VAULT`
  placeholder in committed config, never a real value.
- **Flag in the PR description**: this is a second inter-service auth scheme
  alongside `X-Gateway-Key`; operator to reconcile (see README).

### 3. Idempotency

- `Idempotency-Key` header (required). On a duplicate key within a retention
  window, return `202` **without** re-recording — the gateway retries on
  network failure and must not double-write the chain.
- Minimal store: a new small table `audit_emit_idempotency` (`key` PK,
  `created_at`) with the recorded `event_id`, or reuse an existing idempotency
  mechanism if one already exists in CP-API (check `src/` first — do not
  duplicate). Atomic insert; on conflict treat as duplicate.

## Tests (pytest, test-first, capture red-before-green)

`test_regression_cab_2227_*` files; use the real async test DB, do not mock the
session.

- `test_regression_cab_2227_audit_emit_records_deny_event` — deny payload →
  202 + an `AuditEvent` row with `outcome="failure"`.
- `test_regression_cab_2227_audit_emit_rejects_bad_hmac` → 401.
- `test_regression_cab_2227_audit_emit_rejects_stale_timestamp` → 401.
- `test_regression_cab_2227_audit_emit_is_idempotent` — same `Idempotency-Key`
  twice → one row, both 202.
- `test_regression_cab_2227_audit_emit_validates_payload` — missing required
  field → 422.

## Constraints

- **PR ≤ 300 LOC**; if exceeded split (auth+idempotency infra / endpoint+tests).
- cp-api coverage ≥70%, never lower.
- Validation: lint, `mypy` if configured, `pytest` for touched paths — show the
  output line for every regression test.
- Secrets: Vault only, placeholders, never commit a key.
- Do not touch the gateway.

## Deliverable

Draft PR to `main`, body `Linear: [CAB-2227]`. Report: final insertion count,
the frozen request schema + HMAC signing-string definition (PR 3 must match it
byte-for-byte), and the idempotency-key semantics.
