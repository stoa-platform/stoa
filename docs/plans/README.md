# Plans — Canonical Plan Registry

Canonical location for plans that match the **Decision Challenge Gate** triggers (see `stoa-docs/HEGEMON/DECISION_GATE.md`).

## When to create a plan file here

Create a plan file here **before starting execution** if the plan matches **≥ 1** trigger:

- **(a)** Estimated agent time > 5 h (≈ 2 Linear pts).
- **(b)** Direct business impact: GTM, pricing, positioning, strategic content, partnership, heavy roadmap.
- **(c)** Irreversible: data, contracts, branding, trademark, public commitments.

Plans that do **not** match any trigger stay in chat or `plan.md` — no canonical file required.

## Naming

`YYYY-MM-DD-<slug>.md` — ISO date + short kebab slug.

## Required frontmatter

```yaml
---
id: plan-YYYY-MM-DD-<slug>
triggers: [a, b, c]                    # list of trigger letters matched
validation_status: draft               # draft | challenged | validated | rejected
challenge_ref: docs/decisions/YYYY-MM-DD-<slug>.md   # set once challenged
---
```

## Validation status lifecycle

| Status | Meaning |
|--------|---------|
| `draft` | Plan written, challenger not yet invoked |
| `challenged` | External challenger verdict produced, arbitrage pending |
| `validated` | Arbitrage acted, reframe applied if needed, other gates satisfied |
| `rejected` | Plan abandoned |

## Enforcement

**Convention, not code.** No pre-execution hook. Discipline enforced by CLAUDE.md / AGENTS.md rule: *no execution of a plan with `triggers: [...]` until `validation_status: validated`.*

If discipline breaks ≥ 3 times in 30 days, promote to pre-commit / PreToolUse hook (P2).

## Linked verdict

Every plan in `challenged` / `validated` / `rejected` state **must** reference a verdict file in `docs/decisions/` via `challenge_ref`. The verdict file carries the challenger's reasoning and the final arbitrage.

## Template

See `_template.md`.

## Canonical example

`2026-04-19-dev-tools-gateway.md` — first retroactive application, resulting in `rejected` (Decision Gate log #7).
