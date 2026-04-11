---
name: council
description: Run 8-persona Council validation on a feature/ADR, then auto-create a Linear ticket if score >= 8/10.
argument-hint: "<description of what to build>"
---

<!--
Persona definitions are CANONICAL in `hegemon/patterns/validation/HEG-PAT-003-team-coca-adversarial-validation.md`.
This skill is the runtime invocation surface for that canonical pattern. The 8 personas (Chucky, N3m0, Gh0st,
Pr1nc3ss, OSS Killer, Archi 50x50, Better Call Saul, Gekk0) are mandatory for all formal Council validations.
Do NOT add, remove, or rename personas here without first updating HEG-PAT-003 (canonical-first ordering).
See ADR-061 (stoa-docs) for the architectural decision record.
-->

# Council Validation — $ARGUMENTS

## Three-Stage Council

This skill drives **Stage 1 (ticket pertinence)** and **Stage 2 (plan validation)** — both prose-based, **8-persona scoring** per the canonical Team Coca jury (HEG-PAT-003).

**Stage 3 (code review)** runs **after implementation** on the actual diff, via `scripts/council-review.sh` (4-axis: conformance, debt, attack_surface, contract_impact). It is **not** invoked by this skill — it is wired to the pre-push hook (CAB-2048) and `council-gate.yml` CI workflow (CAB-2049). See `.claude/rules/council-s3.md` for full docs.

```
S1 (this skill, prose)  →  S2 (this skill, plan)  →  implementation  →  S3 (council-review.sh, diff)  →  merge
```

## Step 1: Gather Context

Read and understand the feature/ADR/change description. Gather context from:
- `memory.md` — current sprint, related work
- `plan.md` — where this fits in priorities
- Relevant code files if technical

## Step 1b: Context Compiler — Impact Score

Run the Context Compiler to get the blast radius **before** scoring:

1. Determine the primary component from $ARGUMENTS (or from the ticket description if CAB-XXXX is provided)
2. Run: `docs/scripts/build-context.sh --component <component> --intent "$ARGUMENTS"`
   - If a ticket ID is available: add `--ticket "CAB-XXXX"`
3. Read the generated context pack in `docs/context-packs/`
4. Extract the **Impact Score** and level (LOW/MEDIUM/HIGH/CRITICAL)
5. Include the Impact Score in each persona's evaluation context
6. If **CRITICAL (>= 31)**: flag it explicitly in the Council report header

If `build-context.sh` or `stoa-impact.db` is not available, skip this step with a warning and proceed without impact scoring.

## Step 2: Run the Council — 8 Personas

Evaluate $ARGUMENTS through each of the 8 canonical personas. **All 8 are mandatory** — no subset selection, no quick mode. The canonical roster is defined in `hegemon/patterns/validation/HEG-PAT-003-team-coca-adversarial-validation.md`.

**Domain N/A baseline (calibration rule from CAB-2054 Phase 4)**: when a ticket does not touch a persona's domain (e.g., a backend infra ticket has no webapp surface for N3m0), score the persona at **8/10** (neutral-positive: "no concern detected"), not 6-7. Lower scores must be backed by an actual identified concern. This rule keeps the 8-persona average stable vs the historical 4-persona baseline (calibration drift < ±0.3 on 4/5 historic tickets).

### 1. Chucky (Devil's Advocate) — Score /10
- Challenges assumptions and finds weaknesses
- Questions: Is this really needed? What could go wrong? What's the hidden complexity? How would I break this?
- Red flags: scope creep, over-engineering, unclear requirements, missing failure modes
- Focus: risk assessment, edge cases, failure modes, penetration testing mindset

### 2. N3m0 (Webapp Security) — Score /10
- Evaluates frontend exposure, UX, accessibility, developer experience
- Questions: What UI surfaces are exposed? Is the keyboard flow valid? Are there a11y blockers? Do error messages leak info? Is the DX of the change reasonable?
- Red flags: missing ARIA, keyboard traps, info-leak in error responses, UI surface that bypasses backend auth, fragile selectors
- Focus: web application security, accessibility (WCAG), UX safety, frontend attack surface

### 3. Gh0st (Supply Chain) — Score /10
- Evaluates dependencies, SBOM, lockfile integrity, transitive trust
- Questions: What new deps does this pull? Are they pinned? Lockfile drift? Any transitive CVEs? Is the source repo trustworthy?
- Red flags: unpinned versions, dep from unknown publisher, lockfile not updated, vendored binary blobs, npm/pip postinstall scripts
- Focus: supply chain security, dependency trust, SBOM hygiene

### 4. Pr1nc3ss (Social Engineering) — Score /10
- Evaluates human factors, trust boundaries, phishing surface
- Questions: How would someone trick a user into bypassing this? What does the failure path teach an attacker? Are error messages too informative? Trust prompts clear?
- Red flags: error messages that enumerate users / disclose internals, ambiguous consent UI, trust dialogs that habituate clicks, copy-paste-prone secret flows
- Focus: human factor in security, trust boundary design, anti-phishing posture

### 5. OSS Killer (VC Skeptique) — Score /10
- Evaluates market viability, competitive moat, user value
- Questions: Does this differentiate STOA? Would a user pay for this? Is this a feature or a product? What's the ROI?
- Red flags: me-too features, no measurable impact, building for nobody, parity work without margin uplift
- Focus: competitive advantage, adoption potential, ROI, business viability

### 6. Archi 50x50 (Architecte Veteran) — Score /10
- Evaluates architectural quality, technical debt, scalability
- Questions: Does this follow existing patterns? Is the complexity justified? Will this age well? Does it work at enterprise scale?
- Red flags: wrong abstraction level, coupling, breaking existing contracts, hidden statefulness
- Focus: technical excellence, maintainability, performance, long-horizon evolution

### 7. Better Call Saul (Legal/IP) — Score /10
- Evaluates legal risks, compliance, IP protection, content safety
- Questions: Any license issues? GDPR/DORA compliance? Competitive claims risks? Customer data exposure?
- Red flags: hardcoded secrets, unverified competitive claims, missing disclaimers, GPL contamination, PII leakage
- Focus: legal safety, regulatory alignment, IP protection, compliance posture

### 8. Gekk0 (Monétisation / GTM) — Score /10
- Evaluates revenue alignment, pricing tier fit, time-to-revenue, GTM messaging
- Named after Gordon Gekko ("Wall Street") — ruthless monetization lens. Internal alias.
- Questions: Can we charge for this? Which pricing tier (Open Source / Enterprise / Managed)? Does it shorten the sales cycle? Can sales explain the value prop in 30 seconds?
- Red flags: cool feature with no revenue path, cannibalizes higher-tier offering, sales team can't explain it, misaligned with commercial positioning
- Focus: revenue alignment, pricing tier fit, time-to-revenue, sales enablement, GTM messaging

Present each persona's evaluation:

```
## Council Validation

### Chucky (Devil's Advocate) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences: key concerns or approval>
**Adjustments**: <specific changes required, or "None">

### N3m0 (Webapp Security) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences>
**Adjustments**: <specific changes required, or "None">

### Gh0st (Supply Chain) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences>
**Adjustments**: <specific changes required, or "None">

### Pr1nc3ss (Social Engineering) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences>
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

### Gekk0 (Monétisation / GTM) — X/10
**Verdict**: Go | Fix | Redo
<2-3 sentences>
**Adjustments**: <specific changes required, or "None">

---
**Persona Average**: X.XX/10 (averaged over 8 personas)
**Impact Score**: N (LEVEL) | Modifier: -Y.Y
**Final Score**: X.XX/10
**Global Verdict**: Go | Fix | Redo
**Adjustments to apply**: <numbered list of all adjustments from all 8 personas>
```

## Step 3: Decision Gate

### Impact Score Modifier

The Impact Score from Step 1b applies a risk modifier to the persona average:

| Impact Level | Score Range | Modifier | Rationale |
|-------------|------------|----------|-----------|
| LOW | 0-5 | 0 | Isolated change, no risk adjustment |
| MEDIUM | 6-15 | 0 | Manageable blast radius |
| HIGH | 16-30 | -0.5 | Significant cross-component risk |
| CRITICAL | 31+ | -1.0 | Major blast radius, forces careful review |

**Final Score** = Persona Average + Impact Modifier

If Step 1b was skipped (no DB), Impact Modifier = 0.

### Verdict Thresholds (applied to Final Score)

| Final Score | Action |
|-------------|--------|
| >= 8.0 | **Go** — Auto-create Linear ticket (Step 4) |
| 6.0 - 7.9 | **Fix** — List adjustments, ask user to confirm, then create ticket |
| < 6.0 | **Redo** — Fundamental issues, do NOT create ticket. Propose alternatives. |

## Step 3b: Apply Stage 1 Label on Linear

After scoring, apply the appropriate **Stage 1** label to the Linear ticket (if one exists or is being created):

| Score Range | Label | Color |
|-------------|-------|-------|
| >= 8.0 | `council:ticket-go` | green (#0e8a16) |
| 6.0 - 7.9 | `council:ticket-fix` | amber (#e4b400) |
| < 6.0 | `council:ticket-redo` | red (#d73a49) |

Apply via: `linear.update_issue(id, labels: [existing_labels..., "council:ticket-go|fix|redo"])`

If the ticket already has a `council:ticket-*` label, **replace** it (remove old, add new).

## Step 4: Auto-Create Linear Ticket

If Council passes (Go or Fix-then-confirmed), create the ticket using Linear MCP:

```
linear.create_issue(
  title: "<type>(scope): <short description>",
  description: <see template below>,
  team: "<LINEAR_TEAM_ID>",
  project: "<LINEAR_PROJECT_ID>",
  assignee: "<LINEAR_ASSIGNEE_ID>",
  estimate: <fibonacci points>,
  priority: <1=Urgent, 2=High, 3=Normal, 4=Low>,
  labels: [<type label>, <priority label>, "hlfh:validated", "council:ticket-go|fix", "instance:<detected-instance>"],
  state: "Todo"
)
```

### Issue Description Template

```markdown
## Context
<1-2 paragraphs: what and why>

## Council Validation — X.XX/10 {Go|Fix} | Impact: N (LEVEL, modifier -Y.Y)

| Persona | Score | Verdict |
|---------|-------|---------|
| Chucky (Devil's Advocate) | X/10 | Go |
| N3m0 (Webapp Security) | X/10 | Go |
| Gh0st (Supply Chain) | X/10 | Go |
| Pr1nc3ss (Social Engineering) | X/10 | Go |
| OSS Killer (VC Skeptique) | X/10 | Go |
| Archi 50x50 (Architecte Veteran) | X/10 | Go |
| Better Call Saul (Legal/IP) | X/10 | Go |
| Gekk0 (Monétisation / GTM) | X/10 | Go |

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

## Step 4b: Stage 2 — Plan Validation

After ticket creation and before implementation begins, run **Stage 2** to validate the implementation plan.

### When Stage 2 Runs

| Level | Stage 2? | Trigger |
|-------|----------|---------|
| L1 Issue-to-PR | **Yes** | `/go` triggers Stage 2, `/go-plan` triggers implement |
| L3 Linear Dispatch | **Yes** | `/go` triggers Stage 2, `/go-plan` triggers implement |
| L3.5 Autopilot | No (batch, Stage 1 only) | Unchanged |
| L5 Multi-Agent | No (batch, Stage 1 only) | Unchanged |
| `/council` local | **Yes** | `/council plan "..."` triggers Stage 2 |

### Stage 2 Rubric (same 8 personas as Stage 1, plan-focused questions)

### 1. Chucky (Devil's Advocate) — Score /10
- Risks documented? Edge cases covered by tests?
- Failure modes identified? Rollback plan?
- Hidden dependencies that could block?

### 2. N3m0 (Webapp Security) — Score /10
- Does the UI plan address a11y (keyboard, screen reader, ARIA roles)?
- Are exposed UI surfaces (new routes, public endpoints) enumerated?
- Do error responses leak internal info? Are user-input boundaries validated?
- Is the DX of the change reasonable for downstream consumers?

### 3. Gh0st (Supply Chain) — Score /10
- Are new deps pinned with integrity hashes? Lockfile updated?
- Any dep from an untrusted publisher? Transitive CVE check?
- Vendored binaries? Postinstall scripts?
- SBOM regeneration documented?

### 4. Pr1nc3ss (Social Engineering) — Score /10
- Do error messages enumerate users / disclose internals?
- Trust prompts / consent UI clear and unambiguous?
- Any copy-paste-prone secret flows? Habituated trust dialogs?
- Anti-phishing posture preserved?

### 5. OSS Killer (VC Skeptique) — Score /10
- LOC justified? Delivers the announced value?
- ROI of dev effort vs. user impact?
- Could this be done simpler? Faster alternative explored?

### 6. Archi 50x50 (Architecte Veteran) — Score /10
- Right level of abstraction? Existing patterns respected?
- Breaking changes documented? Migration path clear?
- Test strategy adequate? Statefulness explicit?

### 7. Better Call Saul (Legal/IP) — Score /10
- No secrets hardcoded in the plan? GDPR/DORA impacts noted?
- License implications of new dependencies (incl. transitive)?
- Content safety of any new user-facing text?
- Customer data exposure path?

### 8. Gekk0 (Monétisation / GTM) — Score /10
- Does the plan preserve the monetization hook? Pricing tier boundary intact?
- Breaking change to commercial offering? Cannibalization risk?
- Post-merge marketing comms needed? Sales team enabled?
- Time-to-revenue acceleration or regression?

### Stage 2 Labels

| Score Range | Label | Color |
|-------------|-------|-------|
| >= 8.0 | `council:plan-go` | teal (#006b75) |
| 6.0 - 7.9 | `council:plan-fix` | dark amber (#b45309) |
| < 6.0 | `council:plan-redo` | dark red (#8b0000) |

Apply via: `linear.update_issue(id, labels: [existing_labels..., "council:plan-go|fix|redo"])`

### Stage 2 Flow

```
Stage 1 passes (council:ticket-go)
  ↓ /go
Claude writes implementation plan (posted as issue comment)
  ↓ plan posted
Stage 2 validates the plan (4 personas, plan-focused rubric)
  ↓ council:plan-go applied to Linear
Comment `/go-plan` to approve and start implementation
```

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

## Step 4c: Stage 3 — Automated Code Review (post-implementation)

Stage 3 is **not run by this skill**. It runs automatically against the diff once implementation is complete, via `scripts/council-review.sh`. Shape:

| Axis | Role |
|------|------|
| `conformance` | Repo conventions, style, naming, structure |
| `debt` | Shortcuts, TODOs, test gaps, premature abstractions |
| `attack_surface` | Input validation, authn/z, secrets, SSRF, PII, CORS, deps |
| `contract_impact` | Cross-component contracts (skipped when `docs/stoa-impact.db` is stale) |

Exit codes: `0` APPROVED (avg >= 8.0), `1` REWORK, `2` technical failure.

Trigger points (when wired):

| Level | Trigger | How |
|-------|---------|-----|
| Local pre-push | `git push` | Pre-push hook extension (CAB-2048) |
| CI | PR opened | `.github/workflows/council-gate.yml` feature-flagged via `vars.COUNCIL_S3_ENABLED` (CAB-2049) |
| Manual | Any diff | `scripts/council-review.sh --ticket CAB-XXXX --diff <range>` |

When S3 returns REWORK, address the per-axis blockers/warnings and re-run. Full documentation: `.claude/rules/council-s3.md`.

## Rules

- **Never skip the Council** for features >= 5 pts
- **Always include DoD** in the Linear ticket
- **Adjustments are mandatory** — if a persona says Fix, the adjustment must be in the DoD
- **One ticket per feature** — don't create sub-tasks (those come during implementation)
- **Score honestly** — don't inflate scores to pass the gate
- For **ADRs**: use `/create-adr` skill after Council passes (ADR lives in stoa-docs)
- For **mega-tickets** (>= 30 pts): add `mega-ticket` label automatically
- **Stage 1 labels** (`council:ticket-*`) are applied after every Council scoring (Step 3b)
- **Stage 2 labels** (`council:plan-*`) are applied after plan validation (Step 4b)
