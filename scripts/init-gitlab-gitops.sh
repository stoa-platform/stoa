#!/bin/bash
# Initialize GitLab apim-gitops repository with templates
# This script copies the base structure to a new GitLab repo
set -e

GITLAB_REPO_URL="${GITLAB_REPO_URL:-git@gitlab.com:potomitan/apim-gitops.git}"
TEMPLATES_DIR="$(dirname "$0")/../gitops-templates"
TEMP_DIR=$(mktemp -d)

echo "=== Initializing GitLab GitOps Repository ==="
echo "Repository: ${GITLAB_REPO_URL}"
echo ""

# Clone or create the repo
if git ls-remote "${GITLAB_REPO_URL}" &>/dev/null; then
    echo "Cloning existing repository..."
    git clone "${GITLAB_REPO_URL}" "${TEMP_DIR}/apim-gitops"
else
    echo "Repository doesn't exist. Please create it first on GitLab."
    exit 1
fi

cd "${TEMP_DIR}/apim-gitops"

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
# APIM GitOps Repository

Source of Truth for APIM Platform tenant configurations.

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

- **Control Plane UI**: https://devops.apim.cab-i.com
- **Control Plane API**: https://api.apim.cab-i.com
- **ArgoCD**: https://argocd.apim.cab-i.com

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
read -p "Push to GitLab? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git push origin main
    echo ""
    echo "=== GitLab Repository Initialized ==="
    echo "URL: ${GITLAB_REPO_URL}"
else
    echo ""
    echo "Changes committed locally. Push manually with:"
    echo "  cd ${TEMP_DIR}/apim-gitops && git push origin main"
fi

echo ""
echo "Next steps:"
echo "1. Configure GitLab webhook to Control Plane API"
echo "2. Set GITLAB_TOKEN in Control Plane API"
echo "3. Configure ArgoCD to sync from this repo"
