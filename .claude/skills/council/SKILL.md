---
name: council
description: Run 4-persona Council validation on a feature/ADR, then auto-create a Linear ticket if score >= 8/10.
argument-hint: "<description of what to build>"
---

# Council Validation — $ARGUMENTS

## Step 1: Gather Context

Read and understand the feature/ADR/change description. Gather context from:
- `memory.md` — current sprint, related work
- `plan.md` — where this fits in priorities
- Relevant code files if technical

## Step 2: Run the Council — 4 Personas

Evaluate $ARGUMENTS through each persona:

### 1. Chucky (Devil's Advocate) — Score /10
- Challenges assumptions and finds weaknesses
- Questions: Is this really needed? What could go wrong? What's the hidden complexity?
- Red flags: scope creep, over-engineering, unclear requirements
- Focus: risk assessment, edge cases, failure modes

### 2. OSS Killer (VC Skeptique) — Score /10
- Evaluates market viability, competitive moat, user value
- Questions: Does this differentiate STOA? Would a user pay for this? Is this a feature or a product?
- Red flags: me-too features, no measurable impact, building for nobody
- Focus: competitive advantage, adoption potential, ROI

### 3. Archi 50x50 (Architecte Veteran) — Score /10
- Evaluates architectural quality, technical debt, scalability
- Questions: Does this follow existing patterns? Is the complexity justified? Will this age well?
- Red flags: wrong abstraction level, coupling, breaking existing contracts
- Focus: technical excellence, maintainability, performance

### 4. Better Call Saul (Legal/IP) — Score /10
- Evaluates legal risks, compliance, IP protection, content safety
- Questions: Any license issues? GDPR/DORA compliance? Competitive claims risks?
- Red flags: hardcoded secrets, unverified competitive claims, missing disclaimers
- Focus: legal safety, regulatory alignment, IP protection

Present each persona's evaluation:

```
## Council Validation

### Chucky (Devil's Advocate) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences: key concerns or approval>
**Adjustments**: <specific changes required, or "None">

### OSS Killer (VC Skeptique) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences>
**Adjustments**: <specific changes required, or "None">

### Archi 50x50 (Architecte Veteran) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences>
**Adjustments**: <specific changes required, or "None">

### Better Call Saul (Legal/IP) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences>
**Adjustments**: <specific changes required, or "None">

---
**Average**: X.XX/10
**Global Verdict**: Go | Fix | Redo
**Adjustments to apply**: <numbered list of all adjustments from all personas>
```

## Step 3: Decision Gate

| Average Score | Action |
|---------------|--------|
| >= 8.0 | **Go** — Auto-create Linear ticket (Step 4) |
| 6.0 - 7.9 | **Fix** — List adjustments, ask user to confirm, then create ticket |
| < 6.0 | **Redo** — Fundamental issues, do NOT create ticket. Propose alternatives. |

## Step 4: Auto-Create Linear Ticket

If Council passes (Go or Fix-then-confirmed), create the ticket using Linear MCP:

```
linear.create_issue(
  title: "<type>(scope): <short description>",
  description: <see template below>,
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  project: "227427af-6844-484d-bb4a-dedeffc68825",
  assignee: "0543749d-ecde-4edf-aec1-6f372aafafce",
  estimate: <fibonacci points>,
  priority: <1=Urgent, 2=High, 3=Normal, 4=Low>,
  labels: [<type label>, <priority label>, "hlfh:validated" if applicable],
  state: "Todo"
)
```

### Issue Description Template

```markdown
## Context
<1-2 paragraphs: what and why>

## Council Validation — X.XX/10 {Go|Fix}

| Persona | Score | Verdict |
|---------|-------|---------|
| Chucky (Devil's Advocate) | X/10 | Go |
| OSS Killer (VC Skeptique) | X/10 | Go |
| Archi 50x50 (Architecte Veteran) | X/10 | Go |
| Better Call Saul (Legal/IP) | X/10 | Go |

### Adjustments Applied
1. <adjustment 1>
2. <adjustment 2>

## Scope
<Bullet list of what's in/out of scope>

## Implementation Phases
<Numbered list of phases with estimated LOC>

## DoD
- [ ] <acceptance criteria 1>
- [ ] <acceptance criteria 2>
- [ ] State files updated (memory.md, plan.md)
- [ ] CI green
```

### Estimate Guide

| Complexity | Points | Examples |
|------------|--------|---------|
| Trivial | 1-2 | Config change, docs update, single-file fix |
| Small | 3-5 | Single component, <150 LOC, clear scope |
| Medium | 8-13 | Multi-component, <300 LOC, needs design |
| Large | 21-34 | Cross-cutting, >300 LOC, multiple PRs |
| Epic | 55+ | Multi-sprint, architectural change |

### Priority Mapping

| Signal | Priority | Linear Label |
|--------|----------|-------------|
| Demo blocker, production down | 1 (Urgent) | `P0-Urgent` |
| This week, user-facing | 2 (High) | `P1-High` |
| This sprint | 3 (Normal) | `P2-Medium` |
| Backlog, nice-to-have | 4 (Low) | `P3-Low` |

## Step 5: Update plan.md

After ticket creation, append to the appropriate section in `plan.md`:

```markdown
- [ ] CAB-XXXX: <title> (<points> pts) — Council X.XX/10
```

## Step 6: Report to User

```
Council: X.XX/10 — Go
Ticket: CAB-XXXX (<points> pts)
Linear: <URL>
plan.md: updated
Next: say "go" to start implementation, or "adjust <feedback>" to revise
```

## Rules

- **Never skip the Council** for features >= 5 pts
- **Always include DoD** in the Linear ticket
- **Adjustments are mandatory** — if a persona says Fix, the adjustment must be in the DoD
- **One ticket per feature** — don't create sub-tasks (those come during implementation)
- **Score honestly** — don't inflate scores to pass the gate
- For **ADRs**: use `/create-adr` skill after Council passes (ADR lives in stoa-docs)
- For **mega-tickets** (>= 30 pts): add `mega-ticket` label automatically
