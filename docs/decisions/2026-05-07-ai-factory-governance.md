---
id: decision-2026-05-07-ai-factory-governance
plan_ref: docs/plans/2026-05-07-ai-factory-governance.md
challenger: "GPT-5 (Codex)"
verdict: REFRAME
decision_gate_log: "#11"
erreur_evitee: true
---

# Decision — AI Factory Governance Alignment

## Challenger Prompt

The challenger was asked to pressure-test the framing of `docs/plans/2026-05-07-ai-factory-governance.md`, not to optimize the execution.

Key constraints:

- The challenger was not a persona and was not part of the Internal Council.
- It was explicitly forbidden to simulate Claude personas or optimize for agreement.
- It had to challenge framing, assumptions, governance model, and complexity level.
- It had to avoid scoring, implementation planning, and fake neutrality.

The central questions were whether the real problem is "aligning a new playbook with the existing canon" or whether "the existing canon itself may now need revision because the system evolved"; whether the 8-persona Council, Decision Gate freeze discipline, and 5-category model are useful or ritualized complexity; whether the model improves decision quality or mainly control-feel; and whether STOA is drifting toward governance-centric development.

## Challenger Output

The challenger rejected the protected-canon framing.

The important reframe was:

> The problem is misformulated. It is not mainly "align a new playbook with canon." The existing canon itself now needs review.

The specific evidence was that the governance canon is already inconsistent:

- public `docs/governance/review-loop.md` still describes a 4-persona Council and a 9/10 threshold;
- ADR-061 and current operating rules describe an 8-persona Council and an 8.0 threshold;
- the plan assumes a stable canon to protect, while visible doctrine has already drifted.

The challenger also warned that the 5-category model may be a semantic overlay on a simpler reality. It identified the useful invariant as separation of powers, not taxonomy:

> Canonize the separation-of-powers principle, not the whole taxonomy.

The challenger treated the April 2026 dissolved freeze as a relevant warning: a rule that no longer changes behavior becomes governance theater. It also flagged the risk that STOA could evolve toward governance-centric development, where governance artifacts outnumber shipped product improvements.

## Arbitrage

- **Verdict:** REFRAME
- **Decision:** Do not canonize the full AI Factory governance taxonomy from this draft.
- **Erreur evitee:** YES. The challenge prevented premature over-canonization of an emerging abstraction.

The retained doctrine is narrower:

1. Critical AI-assisted changes require separation of powers: author, reviewer, and merge/risk decision owner must not collapse into the same agent.
2. External challengers must stay non-persona-fed and cognitively distinct from the Internal Council.
3. Irreversible or public-facing decisions require explicit human risk acceptance.
4. PR reviewability remains required, but this decision does not change the 300 LOC rule.

The following are not canonized by this decision:

- the 5-category taxonomy;
- Advisory Agent semantics;
- governance levels;
- expanded Decision Gate triggers;
- detailed role mappings across Claude, GPT, Codex, sub-agents, and skills.

## Consequences

The next valid artifact is not a full multi-agent governance playbook. It is a minimal doctrine for separation of powers in AI-assisted development.

The existing governance canon should be audited for drift before adding new doctrine. At minimum, reconcile the 4-persona versus 8-persona Council descriptions and the 9/10 versus 8.0 thresholds before claiming the canon is stable.

No edit to `stoa-docs/HEGEMON/DECISION_GATE.md` is authorized while its discipline freeze is active. If a log entry is appended later, it should record the REFRAME and the avoided error, not validate this draft.

## Reopen Conditions

Revisit broader canonization only if at least one of these is true:

- a real incident shows role collapse caused a critical miss;
- external contributors report confusion that a minimal doctrine does not solve;
- Council and Decision Gate docs have first been reconciled into one coherent baseline;
- measured evidence shows the 5-category model changes decisions or reduces review failures, rather than only improving process legibility.
