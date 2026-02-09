---
description: Git commit, branch, and PR conventions
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
