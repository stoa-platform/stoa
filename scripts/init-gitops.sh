#!/bin/bash
# Initialize GitOps repository with templates (GitLab or GitHub)
# Supports GIT_PROVIDER=gitlab (default) or GIT_PROVIDER=github
set -e

GIT_PROVIDER="${GIT_PROVIDER:-gitlab}"

if [ "$GIT_PROVIDER" = "github" ]; then
  GITHUB_ORG="${GITHUB_ORG:-stoa-platform}"
  GITHUB_GITOPS_REPO="${GITHUB_GITOPS_REPO:-stoa-gitops}"
  REPO_URL="${REPO_URL:-git@github.com:${GITHUB_ORG}/${GITHUB_GITOPS_REPO}.git}"
else
  REPO_URL="${GITLAB_REPO_URL:-git@gitlab.com:cab6961310/stoa-gitops.git}"
fi

TEMPLATES_DIR="$(dirname "$0")/../gitops-templates"
TEMP_DIR=$(mktemp -d)

echo "=== Initializing GitOps Repository (provider: ${GIT_PROVIDER}) ==="
echo "Repository: ${REPO_URL}"
echo ""

# Clone or create the repo
if git ls-remote "${REPO_URL}" &>/dev/null; then
    echo "Cloning existing repository..."
    git clone "${REPO_URL}" "${TEMP_DIR}/stoa-gitops"
else
    echo "Repository doesn't exist. Please create it first on ${GIT_PROVIDER}."
    exit 1
fi

cd "${TEMP_DIR}/stoa-gitops"

# Copy base files
echo "Copying base configuration..."
cp "${TEMPLATES_DIR}/_defaults.yaml" .
cp -r "${TEMPLATES_DIR}/environments" .

# Create tenants directory structure
mkdir -p tenants

# Create example tenant (optional)
read -p "Create demo tenant? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Creating demo tenant..."
    mkdir -p tenants/demo/{apis,applications,iam,environments}

    # Copy demo tenant files if they exist
    if [ -d "${TEMPLATES_DIR}/../gitops/tenants/demo" ]; then
        cp -r "${TEMPLATES_DIR}/../gitops/tenants/demo/"* tenants/demo/
    fi
fi

# Create README
cat > README.md << 'EOF'
# STOA GitOps Repository

Source of Truth for STOA Platform tenant configurations.

## Structure

```
├── _defaults.yaml           # Global default variables
├── environments/
│   ├── dev/config.yaml     # DEV environment config
│   ├── staging/config.yaml # STAGING environment config
│   └── prod/config.yaml    # PROD environment config
└── tenants/
    └── {tenant_id}/
        ├── tenant.yaml          # Tenant metadata
        ├── environments/        # Tenant-specific overrides
        │   ├── dev.yaml
        │   └── staging.yaml
        ├── apis/
        │   └── {api_name}/
        │       ├── api.yaml     # API configuration
        │       └── openapi.yaml # OpenAPI spec
        ├── applications/
        └── iam/
            └── users.yaml       # IAM users (synced to Keycloak)
```

## Managed by

- **Control Plane UI**: https://console.${BASE_DOMAIN:-gostoa.dev}
- **Control Plane API**: https://api.${BASE_DOMAIN:-gostoa.dev}
- **ArgoCD**: https://argocd.${BASE_DOMAIN:-gostoa.dev}

## Variable Resolution

Variables use `${VAR}` or `${VAR:default}` syntax.

Resolution order:
1. `_defaults.yaml`
2. `environments/{env}/config.yaml`
3. `tenants/{tenant}/environments/{env}.yaml`
4. Inline defaults

## Secrets

Use Vault references for secrets:
```yaml
client_secret: vault:secret/data/tenant/api#client_secret
```
EOF

# Create .gitignore
cat > .gitignore << 'EOF'
# Local
.env
*.local

# IDE
.idea/
.vscode/
*.swp

# Secrets (should use Vault references instead)
**/secrets/
*.secret.yaml
EOF

# Commit and push
echo ""
echo "Committing changes..."
git add .
git commit -m "Initialize GitOps repository structure

- Add global defaults
- Add environment configurations (dev, staging, prod)
- Add tenants directory structure

🤖 Generated with Claude Code"

echo ""
read -p "Push to ${GIT_PROVIDER}? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git push origin main
    echo ""
    echo "=== GitOps Repository Initialized ==="
    echo "URL: ${REPO_URL}"
else
    echo ""
    echo "Changes committed locally. Push manually with:"
    echo "  cd ${TEMP_DIR}/stoa-gitops && git push origin main"
fi

echo ""
echo "Next steps:"
if [ "$GIT_PROVIDER" = "github" ]; then
    echo "1. Configure GitHub webhook to Control Plane API"
    echo "2. Set GITHUB_TOKEN in Control Plane API"
else
    echo "1. Configure GitLab webhook to Control Plane API"
    echo "2. Set GITLAB_TOKEN in Control Plane API"
fi
echo "3. Configure ArgoCD to sync from this repo"
