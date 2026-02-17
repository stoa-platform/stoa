# CAB-456 Implementation: Dependabot for stoa-helm & stoa-web

## Council Validation
- **Score**: 7.8/10 - GO
- **Mode**: Ship (low-risk configuration)
- **Approved**: ✅

## Problem Statement

Expand Dependabot coverage to additional STOA repositories to maintain dependency freshness and security patching across the ecosystem.

## Investigation Findings

### stoa-helm Repository
**Status**: Does not exist as a standalone repository.

**Analysis**:
- Helm charts live in the main monorepo at `charts/`
- GitHub Actions for the monorepo are already covered by existing `.github/dependabot.yml`
- Dependabot does **not support** the "helm" package ecosystem for Chart.yaml dependencies

**Current Helm Charts**:
1. `charts/stoa-platform/` - Platform chart (no external dependencies)
2. `charts/stoa-observability/` - Observability stack with dependencies:
   - alloy 1.5.3
   - tempo 1.24.4
   - prometheus-blackbox-exporter 9.1.0

### stoa-web Repository
**Status**: ✅ Exists at `github.com/stoa-platform/stoa-web`

**Tech Stack**: Astro (npm)

**Action Required**: Add Dependabot configuration

## Implementation

### 1. Helm Chart Dependencies (Monorepo)

**Current State**: Helm chart dependencies in `charts/stoa-observability/Chart.yaml` are not tracked by Dependabot.

**Options**:
- **Manual updates**: Continue updating Chart.yaml dependencies manually
- **Renovate bot**: Alternative tool that supports Helm chart dependencies
- **No action**: Acceptable - Helm charts update infrequently, dependencies are stable

**Decision**: Document the limitation. No automated tracking for Helm dependencies at this time. GitHub Actions for Helm workflows are already covered.

### 2. stoa-web Repository

**Implementation**:

Created helper script `scripts/setup-dependabot-stoa-web.sh` that:
1. Clones the stoa-web repository
2. Creates `.github/dependabot.yml` with npm + GitHub Actions tracking
3. Creates a PR with the configuration

**Configuration**:
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

## Execution Steps

### Automatic (Recommended)
```bash
# Run the helper script
./scripts/setup-dependabot-stoa-web.sh
```

### Manual
```bash
# Clone stoa-web
gh repo clone stoa-platform/stoa-web
cd stoa-web

# Create branch
git checkout -b chore/add-dependabot-config

# Copy the configuration
mkdir -p .github
cp ../stoa/.github/dependabot-stoa-web.yml .github/dependabot.yml

# Commit and push
git add .github/dependabot.yml
git commit -m "chore(ci): add Dependabot configuration (CAB-456)"
git push -u origin chore/add-dependabot-config

# Create PR
gh pr create --fill
```

## Verification

### Immediate
- [ ] PR created in stoa-web repo
- [ ] CI passes on the PR
- [ ] Configuration file is valid YAML
- [ ] PR merged

### Next Monday (First Run)
- [ ] Dependabot PRs appear in stoa-web
- [ ] PRs are limited to 5 per ecosystem
- [ ] Commit messages use correct prefixes
- [ ] PRs are created on Monday as scheduled

## Council DoD Review

Original DoD from Council report:
- [ ] `stoa-helm/.github/dependabot.yml` added with `helm` + `github-actions` ecosystems
- [ ] `stoa-web/.github/dependabot.yml` added with `npm` + `github-actions` ecosystems
- [ ] Both configs use `weekly` schedule, `monday` day, `open-pull-requests-limit: 5`
- [ ] Conventional commit prefix `chore(deps)` configured
- [ ] PRs created in both repos (Ship mode)
- [ ] First Dependabot PRs appear on next Monday (verification)

**Adjusted DoD** (based on investigation):
- [x] Documented that stoa-helm repo doesn't exist
- [x] Documented Helm dependency limitation
- [x] GitHub Actions for monorepo already covered
- [ ] `stoa-web/.github/dependabot.yml` added with `npm` + `github-actions` ecosystems ⬅️ **Pending: requires running script or manual PR**
- [x] Config uses `weekly` schedule, `monday` day, `open-pull-requests-limit: 5`
- [x] Conventional commit prefix `chore(deps)` configured
- [ ] PR created in stoa-web repo ⬅️ **Pending: requires running script**
- [ ] First Dependabot PRs appear on next Monday (verification) ⬅️ **Pending: after merge**

## Files Created

This PR includes:
1. `.github/dependabot-stoa-web.yml` - Template configuration
2. `scripts/setup-dependabot-stoa-web.sh` - Helper script for deployment
3. `docs/DEPENDABOT-EXPANSION.md` - Comprehensive documentation
4. `docs/CAB-456-IMPLEMENTATION.md` - This file

## Next Steps

1. **Merge this PR** to the stoa monorepo (documentation and helper script)
2. **Run the script** to create the stoa-web PR:
   ```bash
   ./scripts/setup-dependabot-stoa-web.sh
   ```
3. **Merge the stoa-web PR** (Ship mode)
4. **Wait for next Monday** to verify Dependabot creates the first dependency update PRs

## Conclusion

The Council report anticipated two standalone repos, but investigation revealed:
- **stoa-helm**: Doesn't exist; Helm charts are in monorepo; Dependabot doesn't support Helm
- **stoa-web**: Exists; requires Dependabot config (script + template provided)

This implementation provides the tools to complete the task while documenting the constraints discovered during implementation.
