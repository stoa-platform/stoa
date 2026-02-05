---
description: Git commit, branch, and PR conventions
---

# Git Conventions

## Commit Messages (commitlint enforced via husky)
- Format: `<type>(<scope>): <subject>` (max 72 chars subject, 100 chars header)
- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`
- **Scopes**: `api`, `ui`, `portal`, `mcp`, `gateway`, `helm`, `ci`, `docs`, `deps`, `security`, `demo`
- Example: `fix(api): escape LIKE wildcards in portal search (CAB-1044)`

## Branch Naming
- `feat/<ticket-id>-<description>` for new features
- `fix/<ticket-id>-<description>` for bug fixes
- Example: `fix/cab-1044-search-escape`

## CI/CD (GitHub Actions)
- **Path-based triggers**: each component has its own workflow
- **Python CI**: ruff lint, mypy, pytest, bandit/safety audit
- **Node CI**: npm install, lint, format check, vitest, coverage
- **Security pipeline**: SAST, dependency audit, gitleaks, SBOM, container scan, DCO check
- **Dependabot**: weekly (Monday), max 5 PRs/ecosystem, prefix `chore(deps)`
