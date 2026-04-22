# Step 5 governance — honest claim contract

**WS 10 (docs) of CAB-2148**. UI portion: CAB-2154. Single source of truth for what the Step 5 screen may state.

## Governing rule

Every Step 5 claim must trace back to a current platform surface that actually shows it. Unmapped claim = over-claim = cut from UI, deck, workshop. Mode narrows the list, never expands it.

## Claim-to-proof map (A + B)

| Claim | Proof source |
|-------|--------------|
| Subscription gate on every MCP call | gateway: anonymous / untied call → 401/403; Portal counter |
| Traceability: subject + subscription per call | Step 4 trace / telemetry |
| Catalog source-of-truth driven (Git) | GitHub catalog repo + Console catalog view |
| Ops surfaces are real ops surfaces | Portal (dashboard) + Console (catalog, subscription) |
| Explicit limits | this doc (limits section below) |

## Claim-to-proof map (Mode A only)

| Claim | Proof | Gate |
|-------|-------|------|
| AI-native live on Step 4 | live trace with `stoa_*` in tool path | JWT evidence green |
| "Same tool, same rules, for APIs and for agents" | gateway: API + MCP calls hit same subject / subscription | Mode A + dry-run green <72h |

## Explicit limits (must be stated, never reworded to sound positive)

- **Portal counts MCP subscriptions only, not API subscriptions.** API-sub-level governance NOT in scope.
- **Rate limiting is not enforced per consumer-scope** on this path (gotcha `rate_limit_dict_getattr`).
- **Contract validation at runtime is not wired on the live gateway.** Schema / contract tests are CI-side.
- **Policy enforcement beyond subscription presence is not demonstrated.** No OPA / policy engine result shown.
- **No regulatory coverage claimed.** No named regulatory framework enforced at demo level.
- **Catalog sync delay is non-zero.** Observable; name it if it shows.

## Forbidden claims (any mode)

- "Full governance" / "complete API governance" / "end-to-end compliance".
- "Regulatory-ready" or any named framework as enforced by the demo path.
- "Same tool, same rules" when Mode B is locked or Mode A dry-run > 72h old.
- Any claim mapping API-sub-level features onto the MCP-sub surface shown.
- Any `segment-banking`-targeted claim when Mode B is locked.

## UI contract (binding for CAB-2154)

(1) Render only claims from the maps above, for the currently locked mode. (2) Render `Explicit limits` visibly — not collapsed by default on first render. (3) Do NOT render any forbidden claim. (4) New UI claims require a prior edit to this doc with a proof source; PRs without the doc edit fail the DoD.

## Plan traceability

Plan constraint 5 (governance = what is visible) → this doc. Constraint 6 (no hidden manipulation) → limits must be visible. Constraint 7 (A/B distinct) → two maps kept separate. Plan Out section (API/MCP sub model convergence) → forbidden-claim list.

## Honesty gap — human call flagged

Lists above are the honest ceiling today. Two items would expand the list only after platform work: (1) **API-sub-level governance on Portal dashboard** — unlocks "governance at API subscription level"; out of demo scope, not planned inside phase-5 window. (2) **Policy engine signal on Step 5** — unlocks "policy enforcement visible"; not wired today. Either landing requires updating **this doc before** adding the corresponding UI claim.

## Cross-links

Mode split: `./proof-contracts/mode-a-vs-mode-b.md`. Gate: `./binary-gate-phase-4.md`. Steps 1-4: `./proof-contracts/step-1-2-declaration-catalogue.md`, `./proof-contracts/step-3-4-subscription-call.md`.
