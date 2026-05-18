# Codex prompt — P0-MCP-1 PR 2 (Gateway: destructive-tool approval gate)

You are implementing **PR 2 of P0-MCP-1** in the STOA monorepo
(`/Users/torpedo/hlfh-repos/stoa`), repo `stoa`, component `stoa-gateway/`
(Rust, Tokio, axum). This is the headline defect fix.

Read first: `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md` §5.3,
`docs/audits/2026-05-11-uac-subscription-mcp/adrs-drafts/adr-067-...md` §4.4,
the sibling README `p0-mcp-1-README.md`, and **PR 1's frozen contract** (the
consume + JWKS endpoint shapes and the pinned `arguments_hash` test vector —
get these from the PR 1 report; do not re-derive them).

## Defect

`requires_human_approval=true` on a UAC operation is never enforced at runtime.
`mcp_tools_call_inner` in `stoa-gateway/src/mcp/handlers.rs` runs
auth → rate-limit → federation → guardrails → budgets → OPA → execution with
**no approval stage**. ADR-067 doctrine is described, not executed.

## Branch / ticket

Branch `feat/cab-2227-mcp-1-gateway-approval-gate` off fresh `origin/main`.
First commit subject carries `CAB-2227`. Conventional commits, scope `gateway`.
Zero-tolerance clippy: `cargo clippy --all-targets -- -D warnings` must be clean,
no unjustified `#[allow]`. `cargo test` (not `--all-features`) locally.

## Scope

### 1. New module — `stoa-gateway/src/mcp/approval_token.rs`

- `struct ApprovalClaims` — deserialize every ADR-067 §4.4 claim: `iss`, `aud`,
  `jti`, `tool_call_id`, `tenant_id`, `tool_name`, `arguments_hash`,
  `policy_version`, `contract_version`, `requester_actor_id`,
  `approver_actor_id`, `iat`, `nbf`, `exp`.
- `enum ApprovalRejectReason` — `Signature`, `Replay`, `ScopeMismatch`,
  `ArgumentsMismatch`, `PolicyVersionMismatch`, `FourEyesViolation`, `Expired`,
  `Missing`, `CpUnreachable`; `as_str()` for stable audit strings.
- `fn canonical_arguments_hash(args: &serde_json::Value) -> String` — the
  README canonical form (keys sorted at every level, no whitespace, lowercase
  hex SHA-256, absent/`null` args hash `{}`). Add a unit test pinning the exact
  same vector value PR 1 pinned — **the test fails if the two disagree**.
- `struct ApprovalTokenVerifier` holding the CP RS256 public key (fetched from
  PR 1's JWKS endpoint; cache it, refresh on unknown `kid` — reuse the
  `auth/oidc.rs` / `auth/jwt.rs` JWKS pattern, `jsonwebtoken` v10).
- `async fn verify(&self, token, ctx: &CallContext) -> Result<ApprovalClaims, ApprovalRejectReason>`
  performing ADR-067 §4.4 gateway verification steps 1, 3, 4, 5, 6 **locally**:
  signature against CP key; `aud=stoa-gateway`; `tenant_id` / `tool_name` /
  `policy_version` / `contract_version` match the active call; `arguments_hash`
  matches `canonical_arguments_hash` of the call's arguments; 4-eyes
  `approver_actor_id != requester_actor_id`; `exp`/`nbf` in bounds.
  Step 2 (`jti` atomic single-use) is **not** done here — see §3.

### 2. CP consume client

Extend `stoa-gateway/src/control_plane/` with a typed client method
`consume_approval_token(jti, tenant_id, tool_name, arguments_hash) -> Result<(), ApprovalRejectReason>`
calling PR 1's `POST /v1/internal/approval-tokens/consume` with the gateway key.
- 200 `{consumed:true}` → `Ok(())`.
- 409 → map `reason` to `ApprovalRejectReason` (`replay` → `Replay`, etc.).
- transport error / non-2xx-non-409 → `CpUnreachable`.

### 3. The approval gate in `mcp_tools_call_inner`

Insert a new stage **after the OPA policy check** (`drop(_opa_span)`, ~line 965)
and **before the semantic-cache / schema-validation step**:

1. Determine if the tool is destructive: the tool's `ToolAnnotations`
   (`mcp/tools/mod.rs`) — `destructive_hint == Some(true)` — OR the contract
   operation's `requires_human_approval`. If neither, **skip the gate**
   entirely (non-destructive tools need no token).
2. Read the `X-Approval-Token` header (`HeaderMap`, same pattern as
   `extract_auth_context`). Absent → reject `Missing`.
3. `ApprovalTokenVerifier::verify(...)` against the call context.
4. On a verified token, call `consume_approval_token(...)` — the atomic
   single-use step. Any non-`Ok` → reject.
5. **Reject path**: respond **403** with a structured MCP error, and emit a
   structured deny audit event — reuse the
   `warn!(audit_event = "tool_call_denied", tenant_id, tool_name, reason, ...)`
   pattern already in `control_plane/tool_permissions.rs`; use
   `audit_event = "approval_token_rejected"` with the `ApprovalRejectReason`
   string. On success emit `audit_event = "approval_token_used"` carrying `jti`.
6. **Config flag** `approval_gate_enabled` (add to `config`, default mirrors
   GW-2's regulated-profile logic: enabled in `prod`/`staging`, off in `dev`
   unless explicitly set). When disabled, log once and skip. When enabled and
   the CP consume call returns `CpUnreachable` → **deny** (fail-closed, ADR-070).

Keep the gate self-contained; do not refactor the surrounding pipeline.

### 4. Tests — `#[cfg(test)] mod tests`, test-first, capture red-before-green

Rust regression tests **must** be named `fn regression_*` (the Regression Test
Guard greps the diff for `fn regression_`; a `// regression for CAB-2227`
comment is NOT detected for Rust). Mark each with a `// regression for CAB-2227`
comment too. Use `wiremock` to stand in for CP's consume + JWKS endpoints; sign
test tokens with a test RSA keypair. Do not mock the gateway boundary under test.

- `regression_destructive_tool_without_approval_token_denies` — 403 + audit event.
- `regression_destructive_tool_with_invalid_signature_token_denies`.
- `regression_destructive_tool_with_wrong_tool_name_token_denies` — `scope_mismatch`.
- `regression_destructive_tool_with_arguments_mismatch_denies` — token for
  `delete(id=A)` rejected on `delete(id=B)`.
- `regression_destructive_tool_with_valid_single_use_token_allows_once` — valid
  token: first call allowed, CP consume returns `replay` on the second → 403.
- `regression_destructive_tool_denies_when_cp_consume_unreachable` — verified
  token but CP consume unreachable → fail-closed 403.
- `regression_non_destructive_tool_does_not_require_approval_token` — no token,
  still allowed.
- `regression_approval_gate_disabled_skips_enforcement` — flag off → no token,
  destructive call proceeds.
- `regression_canonical_arguments_hash_matches_pinned_vector` — the README vector.

## Acceptance criteria (plan §5.3)

- Any destructive `tools/call` with no / invalid / replayed / scope-mismatched /
  arguments-mismatched token → **403**.
- Every 403 emits a structured audit event with a stable `reason`.
- A valid single-use token allows the call exactly once.
- ADR-067 doctrine is executed at runtime, not merely described.

## Constraints

- **PR ≤ 300 LOC.** If exceeded, split: PR 2a = `approval_token.rs` + CP consume
  client + unit tests; PR 2b = the `handlers.rs` gate wiring + integration
  tests. Report which you did.
- `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`
  all clean. Show the output line for every `regression_*` test.
- gateway coverage gate (see `stoa-gateway/CLAUDE.md`) — do not lower it.
- Secrets: test keypair is fine in test code; no real keys committed.

## Deliverable

Open a **draft** PR to `main`, body starting `Linear: [CAB-2227]`, summary +
validation commands. Report the final insertion count and confirm the
`arguments_hash` test vector matches PR 1's pinned value byte-for-byte.
