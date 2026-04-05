---
description: Multi-agent workflow patterns, subagent delegation, cost awareness, plan structure for STOA AI Factory
globs: ".claude/agents/**,.claude/skills/**"
---

# AI Factory — Multi-Agent Workflow

> **HEGEMON Foundation**: Universal AI Factory rules live in `hegemon/rules/ai-factory.md`.
> This file contains STOA-specific extensions (subagents, MCP integrations, delegation patterns).
> **Shared behavioral rules** (Ship/Show/Ask, DoD, State Machine, Logging): see `workflow-essentials.md`.

## Subagents disponibles

| Agent | Model | Outils | Quand utiliser |
|-------|-------|--------|----------------|
| `security-reviewer` | sonnet | Read, Grep, Glob, Bash (RO) | Apres chaque modification de code, PR review, fichiers auth/crypto/secrets/RBAC |
| `test-writer` | sonnet | Read, Grep, Glob, Write, Edit, Bash | Generation de tests, augmentation de couverture |
| `k8s-ops` | sonnet | Read, Grep, Glob, Bash (RO) | Debug deployment, validation manifests k8s, Helm, nginx, rollout, ArgoCD |
| `docs-writer` | sonnet | Read, Grep, Glob, Write, Edit | ADRs, guides, runbooks, memory updates |
| `content-reviewer` | sonnet | Read, Grep, Glob, Bash (RO) | Audit contenu public: concurrents, prix, clients, reglementations |

## MCP Integrations (Claude.ai Native)

Full reference: `.claude/rules/mcp-integrations.md`

| Service | Key Actions | When |
|---------|-------------|------|
| **Linear** | `get_issue`, `update_issue`, `create_comment` | Session start (fetch DoD), PR merge (close ticket), blocked (update status) |
| **Cloudflare** | `search_cloudflare_documentation` | DNS troubleshooting |
| **Vercel** | `list_deployments`, `get_deployment_build_logs` | stoa-web/stoa-docs deploy verification |
| **Notion** | `notion-search`, `notion-fetch` | Cross-workspace knowledge search |
| **n8n** | `execute_workflow` | Trigger automation workflows |

**Rule**: MCP for **state changes**, local files for **context**. Batch reads, minimize writes.

## Cost Awareness

CI model routing and local/subagent model selection: see `cost-model.md`.

## Plan Structure Standard

Every implementation plan MUST follow this structure:

```markdown
# Plan: <ticket-id> — <short title>

## Context
- **Problem**: What's broken or missing (1-2 sentences)
- **Goal**: What success looks like (measurable)
- **Scope**: What's IN and OUT of scope

## Analysis
- **Files to modify** (with line numbers if known):
  - `path/to/file.ext:L42` — reason for change
- **Dependencies and risks**: what could break, what blocks this
- **Alternatives considered**: option A vs B, chosen B because...

## Implementation Steps
1. Step title — (files: `path/to/file.ext`)
   - What to change and why
   - Expected LOC: ~N
   - **Verification**: `<command that proves this step works>`
(Each step independently testable. Dependencies explicit.)

## Binary DoD
Gate 1 (pre-push, local, ~60s): lint + format + compile + axe → enforced by hook on `git push`.
Gate 2 (CI, remote, ~5min): License + SBOM + Signed Commits + Security scans.
→ See `workflow-essentials.md` for full Two-Gate Validation Model + Component checks.

## Ship/Show/Ask
- **Mode**: Ship | Show | Ask (see `workflow-essentials.md` decision matrix)

## Confidence
**[High/Medium/Low]** — <1 sentence justification>
```

## Delegation Patterns

### When to delegate vs work inline
- **Delegate**: verbose output, isolated context, self-contained task, read-only tools needed
- **Inline**: frequent user interaction, shared context, <5 files, latency matters

### Pattern 1-2: Sequential / Parallel Review
- **P1**: security-reviewer → test-writer → k8s-ops (sequential pipeline)
- **P2** (`/parallel-review`): all 3 in parallel → synthesize → Go/Fix/Redo verdict

### Pattern 3: Feature Development (test-first DEFAULT for feat/fix)
`[Inline] Plan → Branch → [test-writer] Failing tests → Implement to pass → [security-reviewer] Review → Push (pre-push gate) → PR → CI → Merge → CD verify → State files`

**Test-first is the default** for all `feat()` and `fix()` tickets. Write failing tests FIRST, then implement to make them pass. This ensures every change has test coverage from the start and prevents regressions. Pattern 5 (code-first) remains available for `refactor()`, `chore()`, `docs()`, `style()`.

**Push = validation gate**: `git push` triggers the pre-push hook which runs lint + format + compile + axe-core automatically. If the push succeeds, checks 1/4/5/6 of the Binary DoD are already proven. Never create a PR from code that hasn't passed the pre-push gate.

### Pattern 4: Agent Teams (opt-in, experimental)
Activation: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Prereq: `tmux`. Max 3 teammates (Sonnet), lead (Opus). Only for multi-component independent scopes >= 300 LOC. Must write `.claude/claims/` files (Claim File Bridge). See `phase-ownership.md`.

### Pattern 5-7: CI-first / Content compliance / Spec-driven
- **P5** (code-first): Branch → code → push (pre-push gate) → tests → security → merge → CD verify. **Only for refactor/chore/docs/style** — never for feat/fix.
- **P6**: docs-writer → content-reviewer → security-reviewer → corrections → PR
- **P7** (Osmani): Plan → test-writer (failing tests first) → implement → security → merge. **Merged into Pattern 3 as default behavior.**

### Pattern 8-9: Decompose + Phase Ownership
- **P8** (`/decompose`): MEGA → N component sub-issues on Linear → N parallel instances/worktrees
- **P9**: `.claude/claims/<ID>.json` coordination. 3 modes: sequential, multi-instance, multi-subagent

Rules: end-to-end phase ownership, max 3 instances, <300 LOC/PR, API=Phase1, UI=Phase2, E2E=last.
See `phase-ownership.md` for full protocol.

## Contraintes

- **Max 3-4 subagents simultaneously**
- **security-reviewer, k8s-ops, content-reviewer** = read-only (never modify code)
- **test-writer, docs-writer** = modify code (verify outputs)
- Binary verdict per subagent: Go / Fix / Redo. One P0 → global **Fix**
- Always consult: `ci-quality-gates.md` (before commit), `secrets-management.md` (credentials), `content-compliance.md` (public content)
- Always update state files after PR merge
