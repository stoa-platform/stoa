---
description: Multi-agent workflow patterns, subagent delegation, cost awareness, plan structure, and binary DoD for STOA AI Factory
---

# AI Factory — Multi-Agent Workflow

## Subagents disponibles

| Agent | Model | Outils | Quand utiliser |
|-------|-------|--------|----------------|
| `security-reviewer` | sonnet | Read, Grep, Glob, Bash (RO) | Apres chaque modification de code, PR review, fichiers auth/crypto/secrets/RBAC |
| `test-writer` | sonnet | Read, Grep, Glob, Write, Edit, Bash | Generation de tests, augmentation de couverture |
| `k8s-ops` | sonnet | Read, Grep, Glob, Bash (RO) | Debug deployment, validation manifests k8s, Helm, nginx, rollout, ArgoCD |
| `docs-writer` | sonnet | Read, Grep, Glob, Write, Edit | ADRs, guides, runbooks, memory updates |
| `content-reviewer` | sonnet | Read, Grep, Glob, Bash (RO) | Audit contenu public: concurrents, prix, clients, reglementations |

## MCP Integrations (Claude.ai Native)

External services connected via Claude.ai MCP servers — no local config needed.
Full reference: `.claude/rules/mcp-integrations.md`

| Service | Key Actions | When |
|---------|-------------|------|
| **Linear** | `get_issue`, `update_issue`, `create_comment` | Session start (fetch DoD), PR merge (close ticket), blocked (update status) |
| **Cloudflare** | `search_cloudflare_documentation` | DNS troubleshooting, Cloudflare docs |
| **Vercel** | `list_deployments`, `get_deployment_build_logs` | stoa-web/stoa-docs deploy verification |
| **Notion** | `notion-search`, `notion-fetch` | Cross-workspace knowledge search |
| **n8n** | `execute_workflow` | Trigger automation workflows |

**Rule**: Use MCP for **state changes** (Linear status, Vercel deploy check). Use local files for **context** (memory.md, plan.md, CLAUDE.md). MCP calls are free but add latency — batch reads, minimize writes.

## Cost Awareness

| Task Type | Model | Rationale |
|-----------|-------|-----------|
| Code exploration, search, analysis | **haiku** | Fast, cheap, sufficient for grep/glob |
| Subagent work (tests, reviews, docs) | **sonnet** | Good balance of quality and cost |
| Architecture decisions, security review | **opus** | Critical decisions need best reasoning |
| Plan review, implementation | **opus** (inline) | Main conversation, full context needed |

**Rules**:
- Never use opus for subagents — cost explodes with fresh context
- Prefer haiku for `Explore` agents (codebase search)
- Sonnet is the default for all 5 subagents
- Maximum **3-4 subagents active simultaneously**

## Plan Structure Standard

Every implementation plan MUST follow this structure. Inspired by AGENTS.md spec, Stripe engineering, and Addy Osmani's AI workflow. Plans are machine-readable documents that enable autonomous execution.

### Mandatory Plan Sections

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
- **Alternatives considered**: (if >1 viable approach) option A vs B, chosen B because...

## Implementation Steps
1. Step title — (files: `path/to/file.ext`)
   - What to change and why
   - Expected LOC: ~N
   - **Verification**: `<command that proves this step works>`
2. ...
(Each step must be independently testable. Dependencies between steps explicit.)

## Binary DoD
- [ ] All modified files listed in Implementation Steps
- [ ] Each step is independently testable
- [ ] Total LOC < 300 (or split into micro-PRs)
- [ ] No new `any` types, `todo!()`, or `// TODO`
- [ ] Component-specific quality gate passes (see below)

## Ship/Show/Ask
- **Mode**: Ship | Show | Ask
- **Rationale**: <why this mode>

## Confidence
**[High/Medium/Low]** — <1 sentence justification>
(If Medium/Low: list open questions before implementation)
```

### PR Size Thresholds (Stripe-inspired)

| Size | LOC Changed | Action |
|------|-------------|--------|
| Ideal | <50 | Auto-merge eligible with tests |
| Good | 50-150 | Single micro-commit |
| Acceptable | 150-300 | Single PR, multiple commits |
| Too large | >300 | MUST split into micro-PRs |

### Binary Definition of Done

A task is DONE if and only if ALL checks pass. No partial credit, no "mostly done".

#### Universal Checks (every task)

| # | Check | Pass Criteria | How to Verify |
|---|-------|--------------|---------------|
| 1 | Code compiles | Zero errors | `cargo check` / `tsc --noEmit` / `ruff check` |
| 2 | Tests pass | Zero failures | `cargo test` / `npm test -- --run` / `pytest` |
| 3 | No regressions | Existing tests still green | Full test suite run |
| 4 | Lint clean | Zero new warnings | Component lint command |
| 5 | Format clean | Zero diffs | `cargo fmt --check` / `npm run format:check` |
| 6 | No secrets | Zero matches | `gitleaks detect --no-git` on changed files |
| 7 | PR created | PR URL exists | `gh pr view` |
| 8 | CI green | 3 required checks pass | `gh pr checks` |
| 9 | State files updated | `memory.md` reflects changes | Manual check |
| 10 | Session logged | SESSION-START exists in operations.log for this task | `tail -20 operations.log` |

#### Component-Specific Checks

| Component | Extra Checks |
|-----------|-------------|
| Python (api, mcp) | Coverage >= threshold, ruff + black clean, mypy clean |
| TypeScript (ui, portal) | ESLint max-warnings not exceeded, prettier clean, tsc clean |
| Rust (gateway) | Clippy zero warnings (strict + SAST rules), cargo test --all-features |
| K8s/Helm | `helm lint`, `privileged: false` present, probes use `/health` |
| Docs/Content | Content compliance scan (no P0/P1 violations) |

#### Post-Merge Checks (code changes only)

| # | Check | Pass Criteria |
|---|-------|--------------|
| 1 | CI on main | Component workflow `conclusion: success` |
| 2 | Docker build | Image pushed to ECR |
| 3 | Pod updated | New image running in `stoa-system` |
| 4 | ArgoCD synced | Synced + Healthy (if ArgoCD-managed) |

## Ship/Show/Ask Decision Matrix

| Change Type | Mode | Examples |
|-------------|------|---------|
| `.claude/` config, rules, prompts | **Ship** | AI Factory rules, agent configs |
| `memory.md`, `plan.md`, docs (`.md`) | **Ship** | State files, runbooks, README |
| Dependency bumps (minor/patch) | **Ship** | Dependabot PRs, lockfile updates |
| Test additions (no code changes) | **Show** | New unit tests, coverage improvement |
| Refactoring (no behavior change) | **Show** | Extract function, rename, reorganize |
| Style/format fixes | **Show** | Prettier, ESLint autofix, ruff format |
| Bug fix (isolated, clear root cause) | **Show** | Off-by-one, null check, typo in logic |
| New feature (any scope) | **Ask** | New endpoint, new component, new model |
| Security-related changes | **Ask** | Auth, RBAC, secrets, crypto, CORS |
| Database migrations | **Ask** | Alembic, schema changes |
| K8s/Helm/infra changes | **Ask** | Deployments, services, ingress, ArgoCD |
| Breaking API changes | **Ask** | Endpoint removal, schema change, renamed fields |
| Cross-component changes | **Ask** | Gateway + API, UI + Portal |

## Quand deleguer vs travailler inline

### Deleguer a un subagent quand:
- La tache produit beaucoup d'output (logs k8s, rapports securite, analyse de couverture)
- On veut isoler le contexte (ne pas polluer la conversation principale)
- La tache est auto-contenue (ecrire des tests, analyser une PR, diagnostiquer un deploy)
- On a besoin d'outils restreints (securite et k8s = read-only par design)

### Travailler inline quand:
- La tache necessite des allers-retours frequents avec l'utilisateur
- Plusieurs phases partagent du contexte significatif
- Le changement est rapide et cible (< 5 fichiers)
- La latence compte (les subagents demarrent avec un contexte frais)

## Patterns de delegation

### Pattern 1: Review sequentielle
```
1. security-reviewer analyse les changements
2. Resultats → test-writer genere les tests manquants
3. k8s-ops valide si des fichiers infra sont modifies
```
Usage: feature development standard, PR review approfondie.

### Pattern 2: Review parallele (/parallel-review)
```
Lancer security-reviewer + test-writer + k8s-ops en parallele
Synthetiser les resultats dans le thread principal
Produire un verdict global Go / Fix / Refaire
```
Usage: PR review rapide, validation pre-merge.

### Pattern 3: Feature development (Ship/Show/Ask)
```
1.  [Inline] Explorer + planifier (Plan mode)
2.  [Inline] Branch: git checkout -b feat/CAB-XXXX-description
3.  [LOG] SESSION-START | task=CAB-XXXX branch=feat/...
4.  [Inline] Implementer le code + micro-commits (<150 LOC chacun)
5.  [test-writer] Generer les tests
6.  [security-reviewer] Review securite
7.  [docs-writer] Documenter si ADR ou guide necessaire
8.  [Inline] Local quality gate (ci-quality-gates.md)
9.  [Inline] Push + PR (gh pr create)
10. [LOG] STEP-DONE | step=pr-created task=CAB-XXXX pr=XXX
11. [Inline] CI green (gh pr checks --watch)
12. [LOG+CHECKPOINT] Before merge — create checkpoint file
13. [Inline] Ship/Show → merge auto | Ask → attendre "merge"
14. [LOG] STEP-DONE | step=merged task=CAB-XXXX pr=XXX — delete checkpoint
15. [Inline] Verify CD: CI main → ArgoCD sync → Pod healthy
16. [k8s-ops] Si ArgoCD OutOfSync ou pod CrashLoop → diagnostiquer
17. [Inline] Update state files (memory.md, plan.md) + cleanup branch
18. [LOG] SESSION-END | task=CAB-XXXX status=success
```
Usage: implementation complete d'un ticket CAB-XXXX. Voir `git-workflow.md` pour Ship/Show/Ask + CD verification map.

### Pattern 4: Agent Teams (opt-in, experimental)

**Activation**: `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` dans `.claude/settings.json` (auto, pas de .zshrc).
**Prerequis runtime**: `brew install tmux`

**IMPORTANT**: Le flag rend la feature disponible. Il ne l'active PAS automatiquement.
Claude ne spawne des teammates que si les criteres ci-dessous sont remplis.

#### Gate de decision — Quand utiliser Agent Teams

```
Tache a realiser ?
│
├── Mono-composant (api, ui, portal, gateway, mcp, e2e)
│   └── ❌ Single session — Agent Teams interdit (overhead inutile)
│
├── Multi-composants MAIS sequentiels (couplage fort)
│   └── ❌ Single session — micro-PRs Stripe (Pattern 5/7)
│
├── Multi-composants ET independants (aucune dependance entre eux)
│   │   Exemples:
│   │   - API endpoints + UI components + tests E2E (3 scopes isoles)
│   │   - Refactoring gateway + refactoring portal (zero couplage)
│   │   - Debug concurrent: 3 hypotheses a tester en parallele
│   │
│   ├── LOC total < 300 ?
│   │   └── ❌ Single session — pas assez de travail pour justifier N contextes
│   │
│   └── LOC total >= 300, 2-3 scopes independants ?
│       └── ✅ Agent Teams (max 3 teammates)
│           Lead: Opus (coordination) | Teammates: Sonnet (implementation)
│
└── User demande explicitement "use teams" / "parallelize"
    └── ✅ Agent Teams — user override, pas de gate
```

#### Regles d'usage

| Regle | Detail |
|-------|--------|
| Max teammates | **3** (au-dela, cout explose sans gain proportionnel) |
| Lead model | Opus (coordination strategique) |
| Teammate model | Sonnet (implementation, cout maitrise) |
| Chaque teammate | 1 scope, 1 branche, 1 micro-PR independante |
| Jamais pour | Docs-only, single-file fix, config changes, memory updates |
| Cost awareness | ~3-4x tokens pour 3 teammates, ~7x avec overhead plan mode |

#### Workflow Agent Teams
```
1. [Lead/Opus] Analyser la tache, identifier N scopes independants
2. [Lead/Opus] Creer le plan: quel teammate fait quoi
3. [Teammate 1/Sonnet] Scope A: branch → code → tests → quality gate
4. [Teammate 2/Sonnet] Scope B: branch → code → tests → quality gate
5. [Teammate 3/Sonnet] Scope C: branch → code → tests → quality gate
6. [Lead/Opus] Synthetiser: verifier coherence, pas de conflit
7. [Inline] Push + PRs + CI green + merge (sequentiel)
8. [Inline] Update state files
```

### Pattern 5: CI-first development (always-green main)
```
1.  [Inline] Branch + implementer la feature + micro-commits
2.  [LOG] SESSION-START | task=<TASK> branch=<BRANCH>
3.  [Inline] Executer le pre-commit checklist (voir ci-quality-gates.md)
4.  [test-writer] Generer les tests + verifier coverage seuil
5.  [security-reviewer] Review securite + secrets
6.  [LOG+CHECKPOINT] Before merge — create checkpoint file
7.  [Inline] Push + PR + CI green + merge (voir git-workflow.md)
8.  [LOG] STEP-DONE | step=merged — delete checkpoint
9.  [Inline] Verify CD: CI main + ArgoCD + Pod (voir git-workflow.md step 7)
10. [k8s-ops] Si probleme CD → diagnostiquer et proposer fix
11. [Inline] Update state files
12. [LOG] SESSION-END | task=<TASK> status=success
```
Usage: tout changement de code. Objectif: zero surprise en CI, always-green main.

### Pattern 6: Content compliance review
```
1. [docs-writer] Rediger le contenu
2. [content-reviewer] Scanner conformite (concurrents, prix, clients, reglementation)
3. [security-reviewer] Si contenu touche securite/RBAC
4. [Inline] Corrections + commit + PR
```
Usage: tout contenu public avec mentions concurrents, reglementations ou clients.

### Pattern 7: Spec-driven development (Osmani-inspired)
```
1.  [Inline] User provides feature request
2.  [Inline] Claude generates plan in Plan Mode (plan structure standard above)
3.  [Inline] User approves or iterates on plan
4.  [LOG] SESSION-START | task=<TASK> branch=<BRANCH>
5.  [test-writer] Generate failing tests from plan (test-first)
6.  [Inline] Implement code to pass tests (<300 LOC per PR)
7.  [security-reviewer] Review securite
8.  [Inline] Local quality gate (all DoD checkboxes green)
9.  [Inline] Ship/Show/Ask categorization (decision matrix)
10. [LOG+CHECKPOINT] Before merge — create checkpoint file
11. [Inline] PR + CI + merge
12. [LOG] STEP-DONE | step=merged — delete checkpoint
13. [Inline] CD verification (post-merge checks)
14. [Inline] Update state files (memory.md, plan.md)
15. [LOG] SESSION-END | task=<TASK> status=success
```
Usage: all new features. Objective: test-first + quality parity with human code.

### Pattern 8: Decompose + Parallel Instances (multi-Claude)

Prerequis: MEGA ticket (>= 21 pts) touching >= 2 components.
Trigger: `/decompose CAB-XXXX` skill.

```
1.  [Inline] /decompose CAB-XXXX → creates N component-scoped sub-issues on Linear
2.  [Inline] Review the DAG and execution plan
3.  User launches N Claude Code instances (terminals or worktrees)

    Phase 1 (parallel — no dependencies):
4a. [Instance 1] CAB-XXXX-API: branch → code → tests → PR → merge
4b. [Instance 2] CAB-XXXX-GW:  branch → code → tests → PR → merge
4c. [Instance 3] CAB-XXXX-DOCS: branch → write → PR → merge (stoa-docs repo)

    Phase 2 (parallel — after Phase 1 merges):
5a. [Instance 1] CAB-XXXX-UI:    branch → code → tests → PR → merge
5b. [Instance 2] CAB-XXXX-PORTAL: branch → code → tests → PR → merge

    Phase 3 (sequential — after Phase 2):
6.  [Instance 1] CAB-XXXX-E2E:   branch → tests → PR → merge

7.  [Inline] Update parent ticket on Linear (Done)
8.  [Inline] Update state files (memory.md, plan.md)
```

Key rules:
- Each instance works in its own worktree: `git worktree add ../<name> feat/<branch>`
- Each sub-issue = 1 PR, < 300 LOC, independently deployable
- API always Phase 1 (upstream data provider)
- UI always Phase 2 (depends on API endpoints)
- E2E always last (needs all components)
- docs always Phase 1 (separate repo, zero code coupling)
- Worktrees share git history but isolate file changes
- **Dropbox gotcha**: create worktrees OUTSIDE Dropbox folder to avoid sync conflicts

Usage: MEGA features (>= 21 pts), cross-component work. Gain: 1.5-2x speedup.
See `/decompose` skill for full DAG generation and Linear integration.

## Contraintes

- **Maximum 3-4 subagents actifs simultanement** (au-dela, le cout explose et le temps de review aussi)
- **security-reviewer, k8s-ops et content-reviewer** sont read-only — ils ne modifient JAMAIS le code
- **test-writer et docs-writer** modifient le code — verifier leurs outputs
- Chaque subagent qui review donne un **verdict binaire**: Go / Fix / Refaire
- Un seul P0 (critique) de n'importe quel subagent → verdict global **Fix**
- **Toujours consulter `ci-quality-gates.md`** AVANT de committer du code
- **Toujours consulter `secrets-management.md`** quand un env var ou credential est ajoute/modifie
- **Toujours consulter `content-compliance.md`** quand du contenu public mentionne concurrents, prix, clients ou reglementations
- **Toujours mettre a jour les state files** (memory.md, plan.md) apres chaque PR mergee
