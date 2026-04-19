---
id: decision-2026-04-19-dev-tools-gateway
plan_ref: docs/plans/2026-04-19-dev-tools-gateway.md
challenger: "GPT-5 (Codex, background exec)"
verdict: NO-GO
decision_gate_log: "#7"
---

# Decision — 3 tools dev via gateway STOA locale

## Challenger prompt

See the verbatim prompt at `stoa-docs/HEGEMON/DECISION_GATE.md` log #7. Prompt structure: context (STOA platform + active C15 cycle state) + plan verbatim + mandate (5 blocks: hidden flaw, under-priced costs, ignored alternatives, metric gaps, brutal verdict) + hard constraints (600 words, French, no disclaimers, no reflexive validation).

## Challenger output

**Hidden flaw.** The plan frames this as a transport/MCP tooling problem when it is actually a workflow-discipline + artefact-format problem. Claude Code and Codex already perform plan/review/status natively. The gateway would interpose a layer between two tools that already work. If the assumption falls, the "unique artefact format" is a fiction (plan/review/status don't have the same needs), and the Go/No-Go criterion is biased (agents will bypass the tool as soon as it adds friction).

**Under-priced costs.**
- **Schemas:** not "x2" but at minimum 3 tools × I/O × 2 clients + artefact compat — silent wording drift = worst bug class
- **Auth:** "minimal" is a lie — CAB-2121 not even committed, so Keycloak + scopes + policy mapping + fallback + 401/403 + rotation + debug to design
- **Latency:** direct CLI is local process; gateway adds MCP discovery + auth + serialization + network hop + wrapper
- **Ops debt:** who fixes k3d/Tilt/gateway/Keycloak when they break? Who versions the artefact when `dev-review` needs a new field?
- **Opportunity cost:** frontal collision with CAB-2088 demo (J-6), CAB-2121 (not secured), CAB-2116 (cost fallout), CAB-2109 (pending) — "1 MEGA per session" rule makes this a collision, not a side quest

**Ignored alternatives.**
1. `stoactl dev plan|review|status` CLI invoked via Bash (2–4 days, 80% of value, zero gateway drift)
2. Shared prompt contract + repo script (1–2 days, tests real demand cheaply)
3. Observe native usage first, instrument nothing (< 1 day, establishes baseline)

**Metric gaps.** No baseline on comparable tickets. No quantified thresholds ("less human routing" = 20%? 50%?). No token/latency cost tracking for the gateway. No quality metrics (false findings, unusable plans, stale statuses, manual workaround rate). No stop-loss (if phase 2 runs X days over, if phase 3 depends on CAB-2121, if Claude/Codex diverge on 1 of 3 tools — when do we stop?).

**Verdict: NO-GO.** Reopen only if three signals exist: CAB-2088 shipped + CAB-2121 merged stable + CAB-2116 fallout absorbed; a no-gateway pilot proves real demand on 10+ tickets; the gateway locale has demonstrated auth/discovery stability on a less fragile use case first.

## Arbitrage

- **Verdict:** NO-GO
- **Rejected because:** the plan mis-frames a workflow-discipline problem as an MCP transport problem, and under-prices auth + ops-debt + opportunity cost against active C15 priorities.

## Reopen conditions

Revisit in 1–3 months only if **all three** hold:

1. CAB-2088 demo shipped, CAB-2121 MCP auth gate merged stable, CAB-2116 cost fallout absorbed
2. A no-gateway pilot (alternative 1 or 2 above) proves real demand on 10+ tickets, with a measured drop in human routing
3. The STOA gateway locale has demonstrated auth + discovery stability on a less fragile use case than the dev workflow itself

## Meta-signal

The Claude → Codex challenge itself was executed during this gate via `codex exec --skip-git-repo-check` + `run_in_background: true` — proving the intended use case (cross-LLM challenge for plan validation) is already achievable with **zero new MCP surface**.
