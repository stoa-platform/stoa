# Dependabot Expansion for STOA Repos

## Overview

This document tracks the expansion of Dependabot coverage to additional STOA repositories as per CAB-456.

## Current Status (Monorepo)

The main `stoa` monorepo has comprehensive Dependabot coverage:
- Python (control-plane-api, mcp-gateway, cli)
- NPM (portal, control-plane-ui, e2e)
- Cargo (stoa-gateway)
- GitHub Actions (root level)
- Docker (root level)

## Helm Chart Dependencies

The monorepo contains Helm charts at `charts/`:
- `charts/stoa-platform/` - Main platform chart (no external dependencies)
- `charts/stoa-observability/` - Observability stack (has dependencies)

### Helm Dependency Limitation

Dependabot does not natively support the "helm" package ecosystem. Helm chart dependencies declared in `Chart.yaml` must be updated manually or via Renovate bot.

### stoa-observability Dependencies

Current Helm dependencies (as of Chart.yaml):
```yaml
dependencies:
  - name: alloy
    version: "1.5.3"
    repository: https://grafana.github.io/helm-charts
  - name: tempo
    version: "1.24.4"
    repository: https://grafana.github.io/helm-charts
  - name: prometheus-blackbox-exporter
    version: "9.1.0"
    repository: https://prometheus-community.github.io/helm-charts
```

**Action Required**: These must be updated manually or consider adding Renovate for Helm chart dependencies.

## stoa-web Repository

**Repository**: `github.com/stoa-platform/stoa-web`
**Tech Stack**: Astro, Node 20

### Recommended Dependabot Config

Create `.github/dependabot.yml` in the stoa-web repo:

```yaml
version: 2
updates:
  # NPM - Astro site
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    commit-message:
      prefix: "chore(deps)"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    commit-message:
      prefix: "chore(ci)"
```

### Implementation Steps for stoa-web

1. Clone the stoa-web repository
2. Create `.github/dependabot.yml` with the above configuration
3. Commit with message: `chore(ci): add Dependabot configuration (CAB-456)`
4. Create PR and merge (Ship mode - low risk)
5. Verify: Dependabot PRs should appear on the following Monday

## Alternative: Renovate Bot

If Helm chart dependency automation is required, consider Renovate bot which supports:
- Helm charts (Chart.yaml dependencies)
- npm, pip, cargo, docker, github-actions
- More flexible configuration than Dependabot

## References

- Dependabot documentation: https://docs.github.com/en/code-security/dependabot
- Existing monorepo config: `.github/dependabot.yml`
- Council report: Issue #664
