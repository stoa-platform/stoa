# Binary decision gate before phase 4

**WS 7 of CAB-2148**. From validated plan phase 4 + Decision Gate #8 (rounds 2 + 4). Locks Mode A or Mode B for the demo cycle. No phase-4 hardening until the gate passes and is signed.

## Rule

Before entering phase 4, exactly one of:

- **Mode A locked** — JWT audience evidence test green AND one dry-run with `stoa_*` in the live path passes.
- **Mode B locked** — JWT evidence not green in phase-3 window OR qualification locks the cycle on restricted promise. `segment-banking` removed from the cycle pipeline.

`Undecided` / `we'll see at dry-run` are not valid states. Gate is **binary**.

## Decision inputs

| Input | Source | Required for |
|-------|--------|--------------|
| JWT audience evidence test result | phase-3 output (CAB-2079 subset: MCP OAuth -> CP API) | Mode A |
| Dry-run trace with `stoa_*` in live path | phase-3 cold run | Mode A |
| Portal sub counter coherent with Step 3 action | phase-3 cold run | A + B |
| Step 5 claim list matched to rendered surfaces | `./step-5-governance-contract.md` + Console UI | A + B |
| Segment list for cycle pipeline | qualification sheet (WS 8) | A + B |

Any Mode A input red → gate falls to Mode B automatically, not to a third mode.

## Sign-off

Locked mode recorded with:

- **Role authorised**: Christophe ABOULICAM (named, not role-only) — Mode B exception owner per validated plan.
- **Timestamp**: UTC date + time.
- **Evidence reference**: JWT evidence output, dry-run trace, qualification sheet.
- **Ban list update**: if Mode B locked, pipeline updated to remove `segment-banking` targets explicitly.

Recorded as a comment on CAB-2148 referencing this doc + evidence pack. Nothing proceeds without that comment.

## Default behaviour

Gate approached without clear Mode A evidence → **Mode B is default**, not Mode A by optimism. Mode B sign-off missing from the named role → **no demo runs**. New info after the gate → a second signed decision required. No silent flip.

## Out of scope

Does not pre-approve individual prospect meetings (per-meeting Mode B still requires the qualification sheet WS 8 + named sign-off for that meeting). Does not validate demo content — cold-run validation (CAB-2155) is a separate gate. Does not authorise re-entering `segment-banking` in Mode B — ban is hard; cannot be waived here.

## No-Go triggers after the gate

An asset states a claim outside the locked mode's `acceptable claims`. Phase 5 or 6 dry-run contradicts the locked mode (e.g. Mode A with broken `stoa_*`). A meeting requests live AI-native proof while Mode B is locked — re-qualify or drop.

## Cross-links

Mode definitions + matrix: `./proof-contracts/mode-a-vs-mode-b.md`. Step oracles: `./proof-contracts/step-1-2-declaration-catalogue.md`, `./proof-contracts/step-3-4-subscription-call.md`. Governance scope: `./step-5-governance-contract.md`. Qualification sheet + Mode B sign-off protocol: WS 8 + WS 9 (separate Phase 1 GTM ticket).
