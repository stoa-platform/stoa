---
description: Git commit, branch, and PR conventions
globs: ".github/**,*.md"
---

# Git Conventions

> Full lifecycle workflow: see `git-workflow.md` (Ship/Show/Ask model)

## Commit Messages (commitlint enforced via husky)
- Format: `<type>(<scope>): <subject>` (max 72 chars subject, 100 chars header)
- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`
- **Scopes**: `api`, `ui`, `portal`, `mcp`, `gateway`, `helm`, `ci`, `docs`, `deps`, `security`, `demo`
- Example: `fix(api): escape LIKE wildcards in portal search (CAB-1044)`
- Include ticket ID: `feat(api): add consumer model (CAB-1121)`

## Branch Naming
- `feat/<ticket-id>-<description>` for new features
- `fix/<ticket-id>-<description>` for bug fixes
- `chore/<ticket-id>-<description>` for maintenance
- `hotfix/<description>` for emergency production fixes
- Example: `feat/cab-1121-consumer-model`

## Merge Strategy
- **Always squash merge** (`--squash`) — one clean commit per feature on main
- Squash message = PR title (conventional commit format)
- Branch auto-deleted on merge (`--delete-branch`)

## CI/CD (GitHub Actions)
- **Path-based triggers**: each component has its own workflow
- **Python CI**: ruff lint, mypy, pytest, bandit/safety audit
- **Node CI**: npm install, lint, format check, vitest, coverage
- **Rust CI**: cargo fmt, clippy (zero warnings), cargo test
- **Security pipeline**: SAST, dependency audit, gitleaks, SBOM, container scan, DCO check
- **Dependabot**: weekly (Monday), max 5 PRs/ecosystem, prefix `chore(deps)`
- **3 required checks** (all PRs): License Compliance, SBOM Generation, Verify Signed Commits

## Release Please

Release Please automates changelogs and version bumps by parsing conventional commits.
It runs on every push to main.

### Config files (DO NOT manually edit without care)
- `.release-please-manifest.json` — current version per component
- `release-please-config.json` — strategy per component (node, python, rust)

### Common failure causes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Fails every push | Commits not parseable as conventional | Check `git log --oneline -10` — ensure `type(scope): subject` format |
| 403 error | Workflow lacks `contents: write` or `pull-requests: write` | Check workflow permissions block |
| Exits non-zero, no PR created | Stale Release Please PR already open | Close the stale RP PR, push an empty commit to re-trigger |
| Version not bumped after `feat:` commit | Commit was a squash merge with non-conventional PR title | Ensure PR title follows `type(scope): subject` format |
| `The release is already up-to-date` | No releasable commits since last release | Normal — not an error, but reported as failure if exit code != 0 |

### Verify Release Please health
```bash
gh run list --workflow=release-please.yml --limit 10
gh run view <run-id> --log | grep -E "error|Error|fail"
```

### Token requirement
The workflow requires either `RELEASE_PLEASE_TOKEN` (PAT with repo scope) or these workflow-level permissions:
```yaml
permissions:
  contents: write
  pull-requests: write
```
