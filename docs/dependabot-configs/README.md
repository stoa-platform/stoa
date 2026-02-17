# Dependabot Configuration for STOA Repositories

This directory contains reference Dependabot configurations for STOA platform repositories.

## Overview

Dependabot automates dependency updates by creating pull requests when new versions are available. This reduces manual toil, improves security posture, and prevents technical debt accumulation.

## Configuration Standard

All STOA repositories use the following Dependabot configuration standard:

- **Schedule**: Weekly, Monday
- **PR Limit**: 5 per ecosystem (prevents PR spam)
- **Commit Prefix**: `chore(deps):` for dependencies, `chore(ci):` for GitHub Actions
- **Conventional Commits**: All commit messages follow conventional commit format

## Repository-Specific Configurations

### stoa-helm

**File**: `stoa-helm-dependabot.yml`

**Ecosystems**:
- `github-actions`: GitHub Actions workflows
- `docker`: Docker images referenced in Helm chart values

**Purpose**: Keep Helm chart dependencies and container image references up to date. Helm charts themselves are updated manually when new app versions are released.

### stoa-web

**File**: `stoa-web-dependabot.yml`

**Ecosystems**:
- `npm`: Astro site dependencies (Node.js packages)
- `github-actions`: GitHub Actions workflows

**Purpose**: Keep Astro website dependencies current, preventing security vulnerabilities and ensuring compatibility with latest Node.js/Astro versions.

## Applying Configurations

To apply these configurations to their respective repositories:

1. **Clone the target repository**:
   ```bash
   # For stoa-helm
   git clone https://github.com/stoa-platform/stoa-helm.git
   cd stoa-helm

   # For stoa-web
   git clone https://github.com/stoa-platform/stoa-web.git
   cd stoa-web
   ```

2. **Create the `.github` directory** (if it doesn't exist):
   ```bash
   mkdir -p .github
   ```

3. **Copy the appropriate configuration**:
   ```bash
   # For stoa-helm
   cp /path/to/stoa/docs/dependabot-configs/stoa-helm-dependabot.yml .github/dependabot.yml

   # For stoa-web
   cp /path/to/stoa/docs/dependabot-configs/stoa-web-dependabot.yml .github/dependabot.yml
   ```

4. **Commit and push**:
   ```bash
   git checkout -b feat/enable-dependabot
   git add .github/dependabot.yml
   git commit -m "chore(ci): enable Dependabot automated dependency updates

- Weekly schedule (Monday)
- Max 5 PRs per ecosystem
- Conventional commit format (chore(deps):)
- Reduces manual toil and CVE exposure

Relates to: stoa-platform/stoa#655"
   git push -u origin feat/enable-dependabot
   ```

5. **Create PR and merge**:
   ```bash
   gh pr create --title "chore(ci): enable Dependabot automated dependency updates" --body "Enable Dependabot to automate dependency updates.

## Changes
- Add .github/dependabot.yml with weekly schedule
- Configure ecosystem-specific update schedules
- Set PR limit to prevent spam

## Benefits
- Reduces manual dependency update toil
- Improves security posture (automated CVE patching)
- Prevents technical debt accumulation

Relates to: stoa-platform/stoa#655"

   # After CI green, merge
   gh pr merge --squash --delete-branch
   ```

6. **Verify Dependabot is active**:
   - Go to repository Settings → Code security and analysis
   - Confirm "Dependabot version updates" is enabled
   - First Dependabot PRs should appear within 1 week (next Monday)

## Maintenance

### Adjusting PR Limits

If too many PRs are created, reduce `open-pull-requests-limit`:

```yaml
- package-ecosystem: "npm"
  directory: "/"
  schedule:
    interval: "weekly"
    day: "monday"
  open-pull-requests-limit: 3  # Reduced from 5
```

### Ignoring Specific Dependencies

To prevent updates for specific packages:

```yaml
- package-ecosystem: "npm"
  directory: "/"
  schedule:
    interval: "weekly"
    day: "monday"
  ignore:
    - dependency-name: "some-package"
      versions: [">=2.0.0"]
```

### Changing Schedule

If weekly updates are too frequent:

```yaml
schedule:
  interval: "monthly"  # Changed from "weekly"
  day: "monday"
```

## Troubleshooting

### No PRs Created After 1 Week

1. Check repository Settings → Code security → Dependabot version updates is enabled
2. Verify `.github/dependabot.yml` is in the repository root
3. Check Dependabot logs: Settings → Code security → Dependabot → View logs
4. Ensure the ecosystem matches the repository structure (e.g., `package.json` exists for npm)

### Too Many PRs

1. Reduce `open-pull-requests-limit` to 3
2. Add `ignore` rules for packages that don't need frequent updates
3. Consider switching to monthly schedule for non-critical dependencies

### CI Failures on Dependabot PRs

1. Review the PR and fix any breaking changes
2. Add version constraints in `package.json` / `Chart.yaml` to prevent breaking upgrades
3. Consider adding pre-commit hooks to catch issues before CI

## References

- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [Configuration Options](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
- STOA Convention: `.claude/rules/git-conventions.md`
