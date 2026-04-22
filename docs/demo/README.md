# Demo runbook — proof contracts package

> Runbook only. Not part of public `stoa-docs`. Internal control surface for the demo multi-client 5-step path.

**Ticket**: CAB-2151 (Phase 1 of CAB-2148). **Plan**: `docs/plans/2026-04-21-demo-multi-client.md` (validated 2026-04-22). **Decision**: `docs/decisions/2026-04-21-demo-multi-client.md` (GO, Gate #8).

## Honesty bar

Demo uses MCP subscription only. Portal counts `MCPServerSubscription`, not `API subscriptions`. Authorised claim family: **control** (subscription gate), **traceability** (subscription + JWT subject per call), **visibility** (real ops surfaces), **explicit limits** (anything not proved is named). Anything beyond is over-claim. Cut.

## Files

| Doc | Scope | WS |
|-----|-------|----|
| `proof-contracts/step-1-2-declaration-catalogue.md` | Steps 1-2 | 4 |
| `proof-contracts/step-3-4-subscription-call.md` | Steps 3-4 | 5 |
| `proof-contracts/mode-a-vs-mode-b.md` | Mode split | 6 |
| `binary-gate-phase-4.md` | Gate + sign-off | 7 |
| `step-5-governance-contract.md` | Step 5 claims | 10 (docs) |

## Reading order

Start with `mode-a-vs-mode-b.md` (mode split gates every other claim) → `binary-gate-phase-4.md` (where Mode A vs Mode B is locked) → walk steps 1-5 via the proof-contracts files + `step-5-governance-contract.md`.

## Downstream consumers

- **Phase 2 Console UI (CAB-2154)** renders Step 5 claims — must trace back to `step-5-governance-contract.md`.
- **E2E cold runs (CAB-2155)** use contracts as test oracles (`expected artefacts` → assertions, `forbidden claims` → negative assertions).
- **Commercial assets** (deck, workshop DSL, one-pagers) must match `acceptable claims`. Caught at asset alignment (WS 11).

## Segment placeholders (public repo; real names live in private `stoa-strategy`)

`segment-industrial`, `segment-utilities`, `segment-services`, `segment-banking` (Mode B hard-banned, plan constraint 5).

## Change control

All edits reviewed by Christophe ABOULICAM before merge. New acceptable claims require a working surface or a plan-level decision log entry.
