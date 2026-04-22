# Step 3-4 proof contract — MCP Subscription + API Call

**WS 5 of CAB-2148**. MCP subscription only (plan constraint 1). No API subscription path in demo.

## Step 3 — MCP Subscription

Surface: subscription path + Portal. Ops actions: observer during demo; seeded by reset harness pre-run.

**Expected artefacts**
- One `MCPServerSubscription` for the Customer API MCP server, visible in Portal + Console.
- Associated MCP credential / config exhibitable (masked).
- Portal MCP counter moves coherently with the action (before/after observable).

**Acceptable claims**
- "Subscription is gated: no MCP call without a subscription tied to a known identity."
- "Portal counts MCP subscriptions — the same objects the run uses."
- "Every subscription has an owner (tenant + persona) traceable in the dashboard."

**Forbidden claims**
- "Subscription covers REST API + MCP in one object." — API subscription out of demo scope.
- "Subscription enforces consumer-scoped rate limits." — not wired (gotcha `rate_limit_dict_getattr`).
- "Subscription grants contract-level operation permissions." — enforcement shown = presence, not operation scope.

**Degraded mode**: if Portal counter lags, show object via Console. Lag named openly. Never swap for an `API subscription` record — invalidates the step.

## Step 4 — API Call

Surface: gateway + runtime. Ops actions: one neutral business call (`GET /customers/{id}` or similar) via the Step 3 subscription.

**Expected artefacts**
- One successful call through the gateway, visible in trace / telemetry, correlated with Step 3 subscription.
- Readable response body on a neutral business field (no mock).
- Trace timeline: consumer -> gateway -> upstream.

**Acceptable claims**
- "Every call is attached to a subscription + subject — no anonymous traffic."
- "Call is observable end-to-end on the same surfaces an ops team uses."
- "Path exercised is the real path — no special bypass."

**Forbidden claims**
- "Gateway enforces AI-native policies on this call." — **Mode A only**, after JWT audience evidence green.
- "Call shows the `stoa_*` tool path." — **Mode A only**. Mode B: `stoa_*` out of live path.
- "Latency / error budgets are enforced." — budgets are observability-level, not enforcement.
- "Call is governed by a contract test at run time." — not wired live.

**Degraded mode**: pre-recorded video backup only if live call fails after the cold-run sequence already proved the path. Announced as backup, not live.

## Oracle of success

Portal subscription counter increments on the action shown. Call responds with a real payload on the neutral scenario. Trace correlates subscription + subject + call — all three in the same surface.

## JWT audience dependency + cross-links

Step 4 `stoa_*` coverage is mode-gated. **Mode A**: JWT fix validated before phase 4 → `stoa_*` in live path. **Mode B**: fix not validated → `stoa_*` removed; Step 4 runs on the neutral business call only. This dependency is the gate hinge. See mode split: `../mode-a-vs-mode-b.md`. Steps 1-2: `./step-1-2-declaration-catalogue.md`. Step 5: `../step-5-governance-contract.md`.
