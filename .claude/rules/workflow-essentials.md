---
description: Core behavioral rules — Ship/Show/Ask, DoD, State Machine, Operation Logging, Anti-Drift
---

# Workflow Essentials — Core Behavioral Rules

> Single source of truth for rules referenced by ai-factory.md, ai-workflow.md, git-workflow.md, session-startup.md, phase-ownership.md.

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

## PR Size Thresholds (Stripe-inspired)

| Size | LOC Changed | Action |
|------|-------------|--------|
| Ideal | <50 | Auto-merge eligible with tests |
| Good | 50-150 | Single micro-commit |
| Acceptable | 150-300 | Single PR, multiple commits |
| Too large | >300 | MUST split into micro-PRs |

## Binary Definition of Done

### Universal Checks (every task)

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
| 10 | Session logged | SESSION-START exists in operations.log | `tail -20 operations.log` |

### Component-Specific Checks

| Component | Extra Checks |
|-----------|-------------|
| Python (api, mcp) | Coverage >= threshold, ruff + black clean, mypy clean |
| TypeScript (ui, portal) | ESLint max-warnings not exceeded, prettier clean, tsc clean |
| Rust (gateway) | Clippy zero warnings (strict + SAST rules), cargo test --all-features |
| K8s/Helm | `helm lint`, `privileged: false` present, probes use `/health` |
| Docs/Content | Content compliance scan (no P0/P1 violations) |

### Post-Merge Checks (code changes only)

| # | Check | Pass Criteria |
|---|-------|--------------|
| 1 | CI on main | Component workflow `conclusion: success` |
| 2 | Docker build | Image pushed to GHCR |
| 3 | Pod updated | New image running in `stoa-system` |
| 4 | ArgoCD synced | Synced + Healthy (if ArgoCD-managed) |
| 5 | Verification proof | Linear comment includes CI link + E2E + pod status |

### Verification Rules (4 non-negotiable)

1. **No DONE without proof** — Linear completion comment MUST include: CI pipeline link, E2E pass/fail, live pod confirmation. No proof = ticket stays open.
2. **E2E co-evolves with code** — Feature/fix tickets MUST update Playwright scenarios in the same PR. No separate "test later" tickets.
3. **CI noise = P0** — Red `main` blocks ALL new work. Fix CI before starting any feature. `/ci-fix` has priority over backlog.
4. **Multi-env gate** — DoD requires 3 proofs: local tests pass, CI pipeline green, staging/prod pod healthy.

### MEGA Close Gate (titles containing `[MEGA]` or has children)

A MEGA ticket CANNOT be marked Done unless ALL of these are true:

| # | Gate | Verification |
|---|------|-------------|
| 0 | MEGA is decomposed | `linear.get_issue(id)` → `children.nodes.length > 0` |
| 1 | Every sub-ticket has a merged PR | Each Done child has a Linear comment containing `PR #` |
| 2 | Linear comment maps items → PRs | Completion comment lists each deliverable + its PR number |
| 3 | Live verification | Target site/endpoint confirmed working (curl, build, or screenshot) |
| 4 | All sub-tickets closed | ALL child issues on Linear are Done (not just the parent) |

**Enforcement**: MEGA Done is blocked at 3 points: manual sessions (Step 5), `linear-close-on-merge.yml`, `claude-linear-dispatch.yml`. See `mega-verification.md` for full protocol.

**If any gate fails**: ticket stays In Progress. Log: `MEGA-GATE-FAIL | task=<ID> missing=<gate_numbers>`

**Use `/verify-mega CAB-XXXX`** to run all gates programmatically before closing.

## Item State Machine (MANDATORY)

```
PENDING ──→ CLAIMED ──→ IN_PROGRESS ──→ DONE ──→ ARCHIVED
   │              │           │
   └── BLOCKED ◄──┴───────────┘
```

### Markers by File

| State | plan.md | memory.md text | memory.md section |
|-------|---------|----------------|-------------------|
| PENDING | `[ ]` | No bold marker | `📋 NEXT` |
| CLAIMED | `[owner: tN]` metadata | Claim file has owner | Phase in claimed MEGA |
| IN_PROGRESS | `[~]` | Sub-items may be ✅ but parent has `[ ]` remaining | `🔴 IN PROGRESS` |
| DONE | `[x]` | `— DONE` suffix or all sub-items ✅ | `✅ DONE` |
| BLOCKED | `[!]` | `— BLOCKED` suffix + reason | `🚫 BLOCKED` |

### Structural Invariants (6 non-negotiable rules)

1. **No DONE in active sections** — completed items MUST be in `✅ DONE` section
2. **Checkbox ↔ section parity** — `[x]` = `✅ DONE`, `[~]` = `🔴 IN PROGRESS`, `[ ]` = `📋 NEXT`
3. **Single home rule** — item appears in exactly ONE section of memory.md
4. **Partial completion** — parent stays `[~]` until ALL sub-items complete
5. **Strikethrough = moved** — remove `~~item~~` within 1 session
6. **MEGA parent stays IN_PROGRESS** until all 5 gates pass — never mark Done directly, always use `/verify-mega`

### Atomic State Transitions

| Transition | plan.md | memory.md | operations.log |
|------------|---------|-----------|----------------|
| Start work | `[ ]` → `[~]` | `📋 NEXT` → `🔴 IN PROGRESS` | — |
| Complete | `[~]` → `[x]` | Add `— DONE (PR #N)` + move to `✅ DONE` | STEP-DONE |
| Block | `[~]` → `[!]` | Move to `🚫 BLOCKED` + add reason | — |
| Unblock | `[!]` → `[~]` | Move back to `🔴 IN PROGRESS` | — |
| Claim phase | — | — | CLAIM |
| Release phase | `[owner: tN]` → `[owner: —]` | — | RELEASE |

**Root cause of past drift**: marking `**DONE**` in text without moving to `✅ DONE` section. Text marker + section move MUST happen together.

## Session-End State Lint (MANDATORY before SESSION-END)

| # | Check | Scan target | Pass criteria |
|---|-------|-------------|---------------|
| 1 | No DONE in IN_PROGRESS | `🔴 IN PROGRESS` section | Zero items with `**DONE**`, `— DONE`, or all-✅ sub-items |
| 2 | No DONE in NEXT | `📋 NEXT` section | Zero items with `**DONE**`, `— DONE`, or `~~strikethrough~~` |
| 3 | Stale `[~]` check | plan.md | Every `[~]` has at least one `[ ]` sub-item remaining |
| 4 | Cross-file parity | plan.md vs memory.md | `[x]` → `✅ DONE`, `[~]` → `🔴 IN PROGRESS` |
| 5 | MEGA close gate | Linear MEGAs marked Done this session | All 5 MEGA gates pass — run `/verify-mega` (see `mega-verification.md`) |

## Operation Logging

Location: `~/.claude/projects/.../memory/operations.log` — append-only.

### Event Types

| Event | Trigger | Required Fields |
|-------|---------|----------------|
| `SESSION-START` | Session begins | `task`, `branch` |
| `SESSION-END` | Session ends | `task`, `status` |
| `STEP-START` | Major step begins | `step`, `task` |
| `STEP-DONE` | Major step completes | `step`, `task` |
| `CHECKPOINT` | Pre-merge checkpoint | `task`, `file` |
| `ERROR` | Non-fatal error | `task`, `error` |
| `RECOVERY` | Crash recovery | `task`, `action` |
| `CLAIM` | Phase claimed | `task`, `phase`, `instance`, `tickets` |
| `RELEASE` | Phase released | `task`, `phase`, `instance`, `reason` |

### Format

`YYYY-MM-DDTHH:MM | EVENT | key=value ...` — one line per event, no multiline.

## Session Metrics

Location: `~/.claude/projects/.../memory/metrics.log` — append-only, same format as operations.log.

| Event | When | Fields |
|-------|------|--------|
| `PR-MERGED` | After merge | `task`, `pr` |
| `CI-FIX` | After `/ci-fix` | `task`, `check`, `auto_fixed` |
| `STATE-DRIFT` | Stop hook detects | `items_misplaced` |
| `PHASE-CLAIMED` | Phase claimed | `task`, `phase`, `instance`, `mode` |
| `PHASE-COMPLETED` | Phase done | `task`, `phase`, `instance`, `pr` |
| `CLAIM-CONFLICT` | Race condition | `task`, `phase`, `winner`, `loser` |

Keep under 500 lines. Rotate oldest to `metrics.log.1` (90-day retention).

## Anti-Drift Rules

- **1 thing at a time** — never mix feature + refactor + fix
- **Never code without a validated plan**
- **Red flags** (broken tests, tech debt, security flaw) → fix before continuing
- **State files are mandatory** — skipping memory.md update is a workflow violation
- **Operation log is mandatory** — every session MUST have SESSION-START and SESSION-END
- **Atomic transitions only** — marking `**DONE**` without moving to `✅ DONE` is forbidden
- **Session-End State Lint** — 5-check lint before every SESSION-END, no exceptions
