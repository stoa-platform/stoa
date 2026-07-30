# P0-MCP-1 — MCP destructive-tool approval gate runtime

Codex implementation prompts for **P0-MCP-1** (PR-P0-3 in the corrective plan
`docs/plans/2026-05-11-uac-subscription-mcp-corrective.md`, `validation_status: validated`).

CAB-2227 / ADR-067 §4.2–§4.4. Defect: a UAC contract can declare
`requires_human_approval=true`, but the gateway never enforces it at
`tools/call` (`stoa-gateway/src/mcp/handlers.rs`). The doctrine is described,
not executed.

## Canonical spec

**ADR-067 §4.4 is the binding doctrine** (challenger condition C4). Where plan
§5.3's claim sketch and ADR-067 §4.4 disagree, **follow the ADR** — §5.3 omits
`arguments_hash`, `policy_version`, `contract_version` and the requester/
approver split, and the ADR explicitly calls such omissions non-compliant.

## Two design decisions baked into these prompts (operator: confirm or override)

1. **`jti` single-use store is CP-side and atomic.** ADR-067 §4.4 invariant 2
   requires the single-use store to be "atomic across replicas". A gateway-local
   moka cache (like `auth/dpop.rs`) is not — under multi-replica it permits
   replay. So the gateway verifies the JWT locally, then calls a CP-API
   endpoint that does an atomic DB compare-and-set to consume the `jti`.
2. **The gateway gate is config-flagged** (`approval_gate_enabled`) for canary
   rollout (plan §12.1), but fail-closed: when enabled and CP is unreachable,
   a destructive call is denied.

## Dependency order

```
PR 1  CP-API   issuance + atomic consume + signing + JWKS   (no gateway dep)
  └─ PR 2  Gateway  approval gate + token verification        (depends on PR 1)
```

PR 1 ships first: issuing tokens nobody consumes yet is harmless. PR 2 starts
enforcing once tokens and the CP public key are already available. PR 2 is
developed/tested against a mocked CP (wiremock) + a test signing key, so it
does not block on PR 1 being merged — only on PR 1's contract being frozen.

## Cross-language invariant — `arguments_hash`

Both PRs MUST hash tool-call arguments identically:

> Canonical form = the arguments JSON object serialized with **object keys
> sorted lexicographically at every nesting level**, **no insignificant
> whitespace**, UTF-8. `arguments_hash` = lowercase hex SHA-256 of those bytes.
> A `null` / absent arguments object hashes the 2-byte string `{}`.

Each PR checks in the **same test vector**:
`{"id":"A","nested":{"b":2,"a":1}}` → canonical
`{"id":"A","nested":{"a":1,"b":2}}` → SHA-256
`9d4e1e23bd5b727046a9e3b4b7db57bd8d6ee684...` (Codex: compute and pin the real
value in both PRs; the test fails if the two languages disagree).

## Files

- `p0-mcp-1-pr1-cp-api.md` — PR 1 prompt
- `p0-mcp-1-pr2-gateway.md` — PR 2 prompt
