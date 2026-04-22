# Mode A vs Mode B — proof contract split

**WS 6 of CAB-2148**. From validated plan `Contrats de preuve par mode` + Decision Gate #8 (rounds 2-3). Mode A and Mode B are **two different demos**, not variants of one run.

## Definitions

| Mode | Definition |
|------|------------|
| **Mode A — Full story** | JWT audience fix validated before phase 4. `stoa_*` re-enter the live path. "Same tool, same rules, for APIs and for agents" demonstrable live on Step 4. |
| **Mode B — Restricted story** | JWT fix not validated OR qualification locks the meeting on the restricted promise. `stoa_*` stay out of live path. Only control / traceability / visibility claims. |

## Per-mode contract

**Mode A**
- Precondition: JWT evidence green + one dry-run with `stoa_*` in the live path before phase 4.
- Expected artefacts: JWT evidence pack, cold run with `stoa_*` in trace, assets aligned on Mode A claim set.
- Acceptable claims: AI-native live via `stoa_*`; "same tool, same rules" (only if live run green); control + traceability + visibility baseline.
- Forbidden claims: "full governance" (surfaces count MCP subs only); "API/MCP subscription convergence demonstrated" (out of plan scope).

**Mode B**
- Precondition: JWT fix not validated OR qualification sheet locks restricted promise.
- Expected artefacts: contractual fallback, assets aligned on restricted claim set, forbidden claims in black and white, reduced segment list.
- Acceptable claims: control, traceability, visibility, explicit limits.
- Forbidden claims: live end-to-end AI-native operability; "same tool, same rules" as demonstrated fact; any `segment-banking`-targeted claim.

## Segment compatibility matrix

Hard rule: Mode B banned on `segment-banking` (plan constraint 5).

| Segment | Mode A | Mode B | Rule |
|---------|--------|--------|------|
| `segment-industrial` | Compatible | Conditional | Mode B only if meeting stays on control / traceability / time-to-first-call |
| `segment-utilities` | Compatible | Conditional | Mode B only if live AI-native is not a prerequisite |
| `segment-services` | Compatible | Conditional | Mode B only if provisioning + visibility gain is the core |
| `segment-banking` | Compatible | **FORBIDDEN** | Hard-banned. Mode B banking-adjacent = out of target. |

`Conditional` is not soft — the pre-demo qualification sheet (WS 8) decides per meeting. Default when sheet missing/ambiguous: **Mode B forbidden**.

## Claim-to-proof traceability

| Claim | Surface | Mode |
|-------|---------|------|
| Control (subscription gate) | Portal + gateway refusal without sub | A + B |
| Traceability (subject + sub per call) | Trace on Step 4 | A + B |
| Visibility (real ops surfaces) | Console, Portal, dashboards | A + B |
| Explicit limits | this doc + step-5 doc | A + B |
| AI-native live (`stoa_*` on Step 4) | Live trace with `stoa_*` path | A only |
| "Same tool, same rules" demonstrated | Trace: APIs + agents hit same gateway / subject | A only, dry-run green |

If a claim is not in this table, it is over-claim. Cut.

## Honesty gap (flagged) + cross-links

Portal counts `MCPServerSubscription` only. Even in Mode A, governance remains partial versus a naive reading of "API governance". Mitigation: Step 5 doc names this explicitly. Steps 1-2: `./step-1-2-declaration-catalogue.md`. Steps 3-4: `./step-3-4-subscription-call.md`. Gate: `../binary-gate-phase-4.md`. Step 5: `../step-5-governance-contract.md`.
