---
name: ci-fix
description: Auto-fix CI failures (lint, format, type errors). Diagnoses, fixes, commits and pushes.
argument-hint: "[PR-number|run-url]"
---

# CI Fix — Auto-remediate CI Failures

## Context dynamique
- Branch courante: !`git branch --show-current`
- Checks PR en cours: !`gh pr checks 2>/dev/null | head -20`
- Workflows recents: !`gh run list --limit 5 --json name,status,conclusion,headBranch --template '{{range .}}{{.name}} | {{.status}} | {{.conclusion}} | {{.headBranch}}{{"\n"}}{{end}}' 2>/dev/null`

## Instructions

Auto-fix CI failure for: $ARGUMENTS

### Step 1: Identify failing checks

If PR number:
```bash
gh pr checks $ARGUMENTS
gh run list --branch $(gh pr view $ARGUMENTS --json headRefName -q .headRefName) --limit 3
```

If workflow run URL or ID:
```bash
gh run view $ARGUMENTS --log-failed
```

### Step 2: Read error logs

```bash
# Get the failed run ID, then read logs
gh run view <run-id> --log-failed 2>&1 | head -200
```

### Step 3: Classify — auto-fixable or manual?

**Auto-fixable** (proceed to Step 4):

| Check | Error pattern | Fix command |
|-------|--------------|-------------|
| Python lint (ruff) | `Found N errors` | `cd <component> && ruff check --fix .` |
| Python format (black) | `would reformat` | `cd <component> && black .` |
| Python import order | `I001` | `cd <component> && ruff check --fix --select I .` |
| TS/JS lint (eslint) | `N problems (N errors, N warnings)` | `cd <component> && npm run lint -- --fix` |
| TS/JS format (prettier) | `Code style issues` | `cd <component> && npx prettier --write .` |
| Rust format | `Diff in` | `cd stoa-gateway && cargo fmt` |
| Rust clippy (simple) | `warning:` with `help: ...` suggestion | `cd stoa-gateway && cargo clippy --fix --allow-dirty` |

**NOT auto-fixable** (report and STOP):

| Category | Examples |
|----------|---------|
| Logic errors | Test assertions failing, wrong behavior |
| Test failures | vitest/pytest/cargo test failures |
| Security issues | Gitleaks, Bandit findings, SAST violations |
| Type errors (complex) | Missing interfaces, wrong generics |
| Build errors | Missing dependencies, Docker build failures |
| Infrastructure | K8s deploy, ArgoCD, Helm issues |

If the failure is NOT auto-fixable, report what you found and stop. Do NOT attempt manual fixes.

### Step 4: Apply fix

Run the appropriate fix command from the table above. Then verify locally:

**Python:**
```bash
cd <component> && ruff check . && black --check .
```

**TypeScript:**
```bash
cd <component> && npm run lint && npm run format:check
```

**Rust:**
```bash
cd stoa-gateway && cargo fmt --check && RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings
```

### Step 5: Commit and push

**GUARDRAILS (mandatory checks before any git operation):**

```bash
# Verify we are NOT on main
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "ABORT: Cannot push CI fixes to main. Checkout the feature branch first."
  exit 1
fi
```

Then commit and push:
```bash
git add <only-fixed-files>
git commit -m "fix(ci): auto-fix <check-name> lint/format issues"
git push
```

### Step 6: Report

```markdown
## CI Fix: [check-name] on [branch]

### Fixed
- **Check**: [failing check name]
- **Error**: [error summary]
- **Fix**: [command run]
- **Files**: [list of modified files]

### Verification
- Local check: PASS/FAIL
- Pushed to: [branch]

### Not Fixed (if any)
- [check]: [reason — requires manual intervention]
```

Append metrics entry:
```
Append to ~/.claude/projects/.../memory/metrics.log:
YYYY-MM-DDTHH:MM | CI-FIX | task=<current-task> check=<check-name> auto_fixed=true|false
```

## Rules

- **NEVER** fix logic errors, test failures, or security issues — only format/lint/type
- **NEVER** push to main — always verify branch name first
- **NEVER** use `--force` push
- **NEVER** use `--no-verify` on commits
- **NEVER** modify test expectations to make them pass
- If the fix changes behavior (not just formatting), STOP and report
- If unsure whether a fix is safe, STOP and report
- Always verify the fix locally before pushing
