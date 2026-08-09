# P0-AUD-2 — minimal Gateway→CP-API audit emit chain

Codex implementation prompts for **P0-AUD-2** (the last Phase 0 item of the
corrective plan `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md`,
`validation_status: validated`). CAB-2227 / ADR-070 §4.6.

Phase 0 does **not** close until P0-AUD-2 lands — challenger condition C1
Option A, plan §1.4 / §3. Without it the global regulator NOGO is not lifted.

## Defect

The gateway emits audit decisions only to local `tracing` (stdout). Tool-call
denies and approval-gated decisions never reach the CP-API audit chain
(ADR-068). A regulator cannot reconstruct "what the gateway decided" from the
authoritative audit store.

## Canonical spec — ADR-070 §4.6 is binding

> `docs/audits/2026-05-11-uac-subscription-mcp/adrs-drafts/adr-070-gateway-fail-closed-posture.md`
> §4.6 (file renumbers to ADR-072 once PR #2788 merges — same document).

**Where plan §6.1 and ADR-070 §4.6 disagree, follow the ADR.** Plan §6.1
sketches a "buffer mémoire borné" (bounded in-memory buffer). ADR-070 §4.6
**explicitly forbids that**: "A simple in-memory buffer with drop-on-overflow
... is forbidden for the critical events in scope." The five mandatory
semantics are: durable on-disk WAL spool, bounded growth with readiness
coupling, no silent drop, replay on recovery, operator observability.

## Phase 0 scope boundary

Phase 0 carries **only denies and approval-gated decisions** — not every
successful call (that is Phase 1, PR-P1-1/P1-2). But the in-scope subset gets
the **full durable semantics** above. Do not expand scope to all events.

## Three PRs

```
PR 1  CP-API   POST /v1/internal/audit/emit  (HMAC auth, idempotent)
PR 2  Gateway  durable WAL spool module       (src/audit/, standalone)
        └─ PR 3  Gateway  emit client + readiness coupling + wiring + metrics
                          (depends on PR 1 contract + PR 2 spool)
```

PR 1 ∥ PR 2 are independent — dispatch in parallel. PR 3 depends on both.

## Open question for the operator — inter-service auth

ADR-070 §4.6 and plan §6.1 specify **HMAC-SHA256** auth for
`/v1/internal/audit/emit`. But the existing CP-API `/v1/internal/*` endpoints
(`gateway_internal.py`, `billing_internal.py`) authenticate with a static
`X-Gateway-Key` header. The prompts implement **HMAC per the ADR** (request
body + timestamp signed, replay-windowed) — stronger, tamper-evident, correct
for an audit channel — but **flag this divergence**: either accept two
inter-service auth schemes, or open a follow-up to unify. Operator decides;
do not silently downgrade to `X-Gateway-Key`.

## Conventions

All three PRs follow the branch / conventional-commit / test-first /
red-before-green / ≤300-LOC-or-split / validation conventions stated in
`p0-mcp-1-pr1-cp-api.md` and `p0-mcp-1-pr2-gateway.md`. Rust regression tests
MUST be named `fn regression_*` (Regression Test Guard). Branch prefix
`feat/cab-2227-aud-2-*`, first commit subject carries `CAB-2227`.

## Files

- `p0-aud-2-pr1-cp-api-emit-endpoint.md`
- `p0-aud-2-pr2-gateway-spool.md`
- `p0-aud-2-pr3-gateway-emit-client.md`
