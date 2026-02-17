#!/bin/bash
set -euo pipefail

# Setup Dependabot for stoa-web repository (CAB-456)
# This script clones stoa-web, adds Dependabot config, and creates a PR

REPO_ORG="stoa-platform"
REPO_NAME="stoa-web"
BRANCH_NAME="chore/add-dependabot-config"
COMMIT_MSG="chore(ci): add Dependabot configuration (CAB-456)"

echo "Setting up Dependabot for ${REPO_ORG}/${REPO_NAME}..."

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "${TEMP_DIR}"' EXIT

cd "${TEMP_DIR}"

# Clone repo
echo "Cloning repository..."
gh repo clone "${REPO_ORG}/${REPO_NAME}"
cd "${REPO_NAME}"

# Create branch
echo "Creating branch ${BRANCH_NAME}..."
git checkout -b "${BRANCH_NAME}"

# Create .github directory if it doesn't exist
mkdir -p .github

# Copy Dependabot config
echo "Adding Dependabot configuration..."
cat > .github/dependabot.yml <<'EOF'
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
EOF

# Commit and push
echo "Committing changes..."
git add .github/dependabot.yml
git commit -m "${COMMIT_MSG}"

echo "Pushing branch..."
git push -u origin "${BRANCH_NAME}"

# Create PR
echo "Creating PR..."
gh pr create \
  --title "${COMMIT_MSG}" \
  --body "$(cat <<'BODY'
## Summary
Adds Dependabot configuration to automate dependency updates for:
- npm packages (weekly, Monday)
- GitHub Actions (weekly, Monday)

## Context
Part of CAB-456: expanding Dependabot coverage across STOA repositories.

## Configuration
- **Schedule**: Weekly on Monday
- **PR limit**: 5 per ecosystem
- **Commit prefix**: `chore(deps)` for npm, `chore(ci)` for GitHub Actions

## Test Plan
- [x] Configuration file follows existing monorepo pattern
- [ ] After merge, verify Dependabot PRs appear on next Monday

## Ship/Show/Ask
**Ship** - Low-risk configuration change, reversible, standard DevOps pattern.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
BODY
)"

echo "Done! PR created for ${REPO_ORG}/${REPO_NAME}"
echo "Next: Merge the PR and wait for Monday to verify Dependabot PRs appear"
