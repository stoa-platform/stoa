# Codex prompt — P0-MCP-1 PR 1 (CP-API: approval-token issuance + atomic consume)

You are implementing **PR 1 of P0-MCP-1** in the STOA monorepo
(`/Users/torpedo/hlfh-repos/stoa`), repo `stoa`, component `control-plane-api/`
(Python 3.11, FastAPI, SQLAlchemy async).

Read first: `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md` §5.3 and
`docs/audits/2026-05-11-uac-subscription-mcp/adrs-drafts/adr-067-uac-describes-mcp-projects-smoke-proves.md`
§4.2–§4.4. **ADR-067 §4.4 is the binding spec.** Also read the sibling README
`p0-mcp-1-README.md` in this directory for the `arguments_hash` canonical form
and the two design decisions — implement exactly that.

## Goal

CP-API issues short-lived, single-use, RS256-signed JWT **approval tokens** that
prove a human approved one specific destructive MCP tool call, and provides an
atomic endpoint the gateway calls to consume a token's `jti` exactly once.

## Branch / ticket

Branch `feat/cab-2227-mcp-1-cp-api-approval-token` off fresh `origin/main`.
First commit subject must carry `CAB-2227`. Conventional commits, scope `api`.

## Scope

### 1. Migration + model — `approval_tokens` table

New Alembic migration + `src/models/approval_token.py` (`ApprovalToken`):

| Column | Type | Notes |
|--------|------|-------|
| `jti` | UUID | **primary key** — the single-use store |
| `tenant_id` | str | indexed |
| `tool_name` | str | `tenant:contract:operation` |
| `tool_call_id` | UUID | correlates to `audit_events.correlation_id` |
| `arguments_hash` | str(64) | lowercase hex SHA-256, README canonical form |
| `policy_version` | str | |
| `contract_version` | str | |
| `requester_actor_id` | str | |
| `approver_actor_id` | str | |
| `issued_at` | timestamptz | |
| `expires_at` | timestamptz | |
| `consumed_at` | timestamptz nullable | NULL = unconsumed |
| `status` | str | `issued` \| `consumed` \| `expired` |

Migration: respect the local-Tilt gotcha — `COMMIT` before any `ADD VALUE` if an
enum is touched (none expected here). Plain table create + indexes.

### 2. Signing — `src/services/approval_token_signer.py`

- RS256. Private key loaded from settings (`approval_token_signing_key`),
  sourced from Vault — **never hardcode**; use a `REPLACE_FROM_VAULT`
  placeholder in any committed config and follow the existing CP-API secret
  pattern (`src/services/` Vault usage). For local dev, allow an env-provided
  PEM.
- Claims, exactly per ADR-067 §4.4: `iss="control-plane-api"`,
  `aud="stoa-gateway"`, `jti`, `tool_call_id`, `tenant_id`, `tool_name`,
  `arguments_hash`, `policy_version`, `contract_version`, `requester_actor_id`,
  `approver_actor_id`, `iat`, `nbf`, `exp`. **TTL = 5 minutes** (configurable
  `approval_token_ttl_seconds`, default 300).
- Use the already-vendored `python-jose` (`from jose import jwt`).

### 3. Service — `src/services/approval_token_service.py`

`ApprovalTokenService`:

- `async issue(*, tenant_id, tool_name, tool_call_id, arguments, policy_version,
  contract_version, requester_actor_id, approver_actor_id) -> str`
  - **4-eyes**: raise `ValueError`/422 if `approver_actor_id == requester_actor_id`.
  - Compute `arguments_hash` (README canonical form — add
    `src/utils/canonical_json.py` with `canonical_hash(obj) -> str`).
  - Persist the `ApprovalToken` row (`status="issued"`), sign the JWT, return it.
  - Audit `APPROVAL_TOKEN_ISSUED` via `AuditService.record_event` (action
    `approval_token_issued`, `resource_type="mcp_tool_call"`,
    `resource_id=tool_name`, `correlation_id=tool_call_id`, `details` carrying
    `jti`, `requester_actor_id`, `approver_actor_id`, `arguments_hash`).
- `async consume(*, jti, tenant_id, tool_name, arguments_hash) -> ConsumeResult`
  - **Atomic CAS**: single
    `UPDATE approval_tokens SET consumed_at=now(), status='consumed'
     WHERE jti=:jti AND consumed_at IS NULL RETURNING *`.
    If 0 rows → already consumed or unknown → reject `replay`.
  - After the row is claimed, verify `tenant_id` / `tool_name` /
    `arguments_hash` match the row and `expires_at > now()`; on mismatch reject
    with the matching reason (`scope_mismatch`, `arguments_mismatch`,
    `expired`). NB: signature/claim verification is the gateway's job — this
    endpoint is the atomic single-use authority only.
  - Audit `APPROVAL_TOKEN_USED` on success, `APPROVAL_TOKEN_REJECTED` (with
    `reason`) otherwise.
  - `reason ∈ {replay, scope_mismatch, arguments_mismatch, expired}`.

### 4. Endpoints

- **Issuance** (approver-facing, human): `POST /v1/tenants/{tenant_id}/tool-approvals`.
  Authenticated user JWT; RBAC `tenant-admin` or `cpi-admin`. The caller is the
  `approver_actor_id`; the body supplies `requester_actor_id`, `tool_name`,
  `tool_call_id`, `arguments`, `policy_version`, `contract_version`. Returns
  `{"approval_token": "<jwt>", "jti": "...", "expires_at": "..."}`.
- **Consume** (gateway-facing): `POST /v1/internal/approval-tokens/consume`.
  Auth via `X-Gateway-Key` — reuse `_validate_gateway_key` from
  `src/routers/gateway_internal.py`. Body `{jti, tenant_id, tool_name,
  arguments_hash}`. Returns 200 `{"consumed": true}` or 409 with
  `{"consumed": false, "reason": "..."}`.
- **Public key** (gateway-facing): expose the RS256 **public** key so the
  gateway can verify signatures. Prefer `GET /v1/internal/approval-tokens/jwks`
  returning a standard JWKS document; `X-Gateway-Key` auth. If a CP-API JWKS
  endpoint already exists for another purpose, extend it instead of adding one
  (check first; do not duplicate).

### 5. Tests (pytest, test-first, capture red-before-green)

`control-plane-api/tests/` — regression tests in `test_regression_*` files OR
named `test_regression_cab_2227_*` (Regression Test Guard convention). Do **not**
mock SQLAlchemy/the DB session — use the existing async test DB fixture.

- `test_regression_cab_2227_issue_rejects_self_approval` — approver == requester → 422.
- `test_regression_cab_2227_consume_is_single_use` — first consume 200, second
  consume same `jti` → 409 `reason=replay`.
- `test_regression_cab_2227_consume_rejects_arguments_mismatch`.
- `test_regression_cab_2227_consume_rejects_expired`.
- `test_regression_cab_2227_consume_requires_gateway_key` — missing/wrong key → 401.
- `test_regression_cab_2227_issued_token_has_all_adr_067_claims` — decode the
  JWT, assert every §4.4 claim is present.
- `test_canonical_hash_vector` — the cross-language test vector from the README.
- Concurrency: `test_regression_cab_2227_consume_atomic_under_race` — fire two
  concurrent `consume(jti)` calls, assert exactly one wins.

## Constraints

- **PR ≤ 300 LOC.** If the diff exceeds it, split into two stacked PRs:
  PR 1a = migration + model + `canonical_json` + signer + service;
  PR 1b = endpoints + audit wiring + endpoint tests. Report which you did.
- Coverage: cp-api gate ≥70%, never lower it.
- `fix()`/`feat()` is test-first; failing tests committed/shown before code.
- Validation must pass: `ruff`/lint, `mypy` if configured, `pytest` for the
  touched paths. Show the output line for every new regression test.
- Secrets: Vault only, `REPLACE_FROM_VAULT` placeholders, never commit a key.
- Do not touch the gateway in this PR.

## Deliverable

Open a **draft** PR to `main`, body starting `Linear: [CAB-2227]`, summary +
the validation commands run. Report: final insertion count, the pinned
`arguments_hash` test-vector value (PR 2 must match it), and the frozen
request/response shapes of the consume + JWKS endpoints (PR 2 depends on them).
