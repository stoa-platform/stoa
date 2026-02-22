---
description: Trunk-based git workflow — Ship/Show/Ask model inspired by GitHub, Stripe, Shopify
globs: ".github/**"
---

# Git Workflow — Trunk-Based Development

> Inspired by GitHub (Ship/Show/Ask + Merge Queue), Stripe (micro-PRs), Shopify (always-green main).

## Golden Rule

**Main is always deployable.** Every merge to main triggers CI + CD + pod update. A broken main = broken production.

## Pre-Authorized Git Operations

When the user validates a plan ("Go") or asks to implement a feature/fix, Claude executes the full git lifecycle **without asking at each step**. These operations are pre-authorized:

- Create feature branch from main
- Stage specific files and commit (conventional commits)
- Push branch to origin
- Create PR via `gh pr create`
- Wait for CI green via `gh pr checks --watch`
- Merge via `gh pr merge --squash --delete-branch`
- Verify post-merge CI/CD

**NEVER ask**: "Should I create a branch?", "Should I commit?", "Should I push?", "Should I create a PR?"

**ALWAYS ask before**: `--force` push, deleting someone else's branch, merging to a non-main branch.

## Ship / Show / Ask

See `workflow-essentials.md` for the full 12-type decision matrix. Claude defaults to **Ship** unless the change matches **Ask** criteria. User can override: "make this an Ask PR" or "just ship it".

### Ship mode (autonomous)
```
branch → code → commit → push → PR → CI green → merge → verify → cleanup
```
No human intervention. Claude handles everything end-to-end.

### Show mode (async review)
```
branch → code → commit → push → PR → CI green → merge → notify user → cleanup
```
Merged immediately. User reviews async. If issues found, fix in follow-up PR.

### Ask mode (blocking review)
```
branch → code → commit → push → PR → CI green → notify user → STOP (wait for "merge")
```
Claude stops after PR creation. User reviews, then says "merge" or "fix X".

## Lifecycle

```
  main (always green, always deployable)
    │
    ├── feat/CAB-XXXX-description ──── micro-commits ──── squash merge ──┐
    │                                                                     │
    ├── fix/CAB-YYYY-description ───── micro-commits ──── squash merge ──┤
    │                                                                     │
    ◄─────────────────────────────────────────────────────────────────────┘
    │
    ▼ CI on main → Docker build → ArgoCD sync → Pod update → CD verified ✅
```

### 1. Branch
```bash
git checkout main && git pull origin main
git checkout -b feat/CAB-XXXX-short-description
```

### 2. Code + Micro-Commits
Commit after each logical unit. Stripe standard: optimal <50 LOC per commit, acceptable <150.
```bash
git add src/models/consumer.py src/schemas/consumer.py
git commit -m "feat(api): add consumer model + schema (CAB-XXXX)"

git add src/repositories/consumer.py
git commit -m "feat(api): add consumer repository (CAB-XXXX)"

git add tests/test_consumer.py
git commit -m "test(api): add consumer unit tests (CAB-XXXX)"
```
- Always `git add <specific-files>` — never `git add .` or `git add -A`
- First commit includes ticket ID, subsequent commits optional
- All commits squashed on merge — commit often, don't overthink messages

### 3. Local Quality Gate
Run checks BEFORE pushing (see `ci-quality-gates.md` for exact commands).

### 4. Push + PR
```bash
git push -u origin HEAD
gh pr create --title "feat(scope): description (CAB-XXXX)" --body "$(cat <<'EOF'
## Summary
- <1-3 bullets: what changed and why>

## Test plan
- [ ] Local quality gate passed
- [ ] CI green

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

After PR created, log the operation:
```
Append to operations.log: STEP-DONE | step=pr-created task=<TASK> pr=<NUMBER> branch=<BRANCH>
```

### 5. CI Green
```bash
gh pr checks <number> --watch
```
3 required checks: License Compliance, SBOM Generation, Verify Signed Commits.
Component CI runs only if relevant paths changed.

If CI fails: fix → commit → push. Same branch, same PR. Never create a new PR for CI fixes.

### 6. Merge

Create checkpoint per `crash-recovery.md` schema, then log: `CHECKPOINT | task=<TASK> file=<CHECKPOINT_FILE>`

```bash
gh pr merge <number> --squash --delete-branch
```
- Always `--squash` — one clean commit per feature on main (Stripe/GitHub standard)
- `--delete-branch` — auto-cleanup remote branch
After successful merge:
- Delete checkpoint file
- Log: `STEP-DONE | step=merged task=<TASK> pr=<NUMBER> sha=<MERGE_SHA>`
- **Linear MCP sync** (if task has CAB-XXXX ID):
  ```
  linear.update_issue("CAB-XXXX", state="Done")
  linear.create_comment(issueId, body="Completed in PR #XXX ...")
  ```

- If strict branch protection blocks merge:
  ```bash
  gh api repos/stoa-platform/stoa/pulls/<number>/update-branch -X PUT -f update_method=merge
  sleep 120  # wait for checks to re-run
  gh pr merge <number> --squash --delete-branch
  ```

### 7. Verify CD (post-merge — MANDATORY for code changes)

After merge to main, Claude MUST verify the full CI + CD pipeline completed. Skip only for docs-only changes (`.md`, `.claude/**`).

**Step 7a — CI on main**
```bash
gh run list --branch main --limit 5 --json status,conclusion,name,headSha
```
Wait until the component workflow shows `conclusion: success`. If it fails, investigate immediately.

**Step 7b — ArgoCD sync status** (for ArgoCD-managed components)
```bash
kubectl get applications -n argocd -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'
```

**Step 7c — Pod health**
```bash
kubectl get pods -n stoa-system -l app=<component> -o wide
kubectl describe deployment/<component> -n stoa-system | grep -E 'Image:|Replicas:|Conditions:'
```

**Step 7d — Report** — summarize to the user:
```
CD Status:
- CI on main: ✅ passed (run #XXXX)
- ArgoCD: ✅ Synced + Healthy (or N/A)
- Pod: ✅ running (image: <tag>)
```
If any step fails, report the error and propose a fix.

After CD verified, log: `STEP-DONE | step=cd-verified task=<TASK> component=<NAME>`

See `ci-quality-gates.md` — "Component → CD verification map" for the full table (CI workflows, ArgoCD apps, deploy methods, AWX, known ArgoCD issues).

### 8. Cleanup
```bash
git checkout main && git pull origin main
git branch -d feat/CAB-XXXX-short-description
```

After cleanup, log session end:
```
Append to operations.log: SESSION-END | task=<TASK> status=success pr=<NUMBER>
```

## Micro-PR Strategy (Stripe-inspired)

Large features MUST be split into stacked micro-PRs:

```
PR #1: feat(api): add consumer model (CAB-XXXX)           ← model + schema + migration
PR #2: feat(api): add consumer CRUD endpoints (CAB-XXXX)  ← repo + router + tests
PR #3: feat(api): add consumer Keycloak sync (CAB-XXXX)   ← integration
PR #4: feat(gateway): propagate consumer ID (CAB-XXXX)    ← cross-component
```

Each PR:
- Is independently deployable (no broken intermediate state)
- Has its own tests
- Is <300 LOC changed (hard limit)
- Merges to main before the next PR starts

This prevents "monster PRs" that are impossible to review and frequently conflict.

## Branch Naming

See `git-conventions.md` — Branch Naming section.

## What Claude NEVER Does

- Force push (`--force`, `--force-with-lease`)
- Push directly to main (always via PR + squash merge)
- Delete branches it didn't create
- Amend published commits
- Skip hooks (`--no-verify`)
- Create empty commits
- Rebase interactive (`-i`)

## Emergency: Hotfix to Production

Only when user explicitly says "hotfix":
```bash
git checkout main && git pull
git checkout -b hotfix/critical-fix
# ... minimal fix ...
git push -u origin HEAD
gh pr create --title "fix: critical description" --body "HOTFIX — needs immediate merge"
# User merges manually or says "merge"
```
