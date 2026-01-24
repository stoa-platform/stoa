#!/bin/bash
# Initialize STOA Platform Bootstrap
#
# This script:
# 1. Validates platform configs
# 2. Syncs configs to GitLab (stoa-gitops)
# 3. Triggers Gateway reconciliation via AWX
# 4. Verifies deployment
#
# Usage: ./scripts/init-platform-bootstrap.sh [--env dev|staging|prod] [--dry-run]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
ENV="dev"
DRY_RUN=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BASE_DOMAIN="${BASE_DOMAIN:-gostoa.dev}"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --env)
      ENV="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--env dev|staging|prod] [--dry-run]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}        STOA Platform Bootstrap Initialization             ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Environment: ${GREEN}$ENV${NC}"
echo -e "Dry Run:     ${YELLOW}$DRY_RUN${NC}"
echo -e "Base Domain: ${GREEN}$BASE_DOMAIN${NC}"
echo ""

# ============================================
# Step 1: Validate Configs
# ============================================
echo -e "${BLUE}[1/5] Validating platform configurations...${NC}"

cd "$PROJECT_ROOT"

if [ -f "scripts/validate-platform-config.py" ]; then
  python3 scripts/validate-platform-config.py --dir deploy/platform-bootstrap
else
  echo -e "${YELLOW}Validation script not found, checking YAML syntax only...${NC}"
  for f in deploy/platform-bootstrap/**/*.yaml; do
    python3 -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null || {
      echo -e "${RED}YAML error in $f${NC}"
      exit 1
    }
  done
fi

echo -e "${GREEN}✓ Validation passed${NC}\n"

# ============================================
# Step 2: Substitute Variables
# ============================================
echo -e "${BLUE}[2/5] Substituting environment variables...${NC}"

TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

cp -r deploy/platform-bootstrap/* "$TEMP_DIR/"

# Substitute variables
find "$TEMP_DIR" -name "*.yaml" -exec sed -i.bak \
  -e "s/\${BASE_DOMAIN}/$BASE_DOMAIN/g" \
  -e "s/\${BASE_DOMAIN:-[^}]*}/$BASE_DOMAIN/g" \
  {} \;

find "$TEMP_DIR" -name "*.bak" -delete

echo -e "${GREEN}✓ Variables substituted${NC}\n"

# ============================================
# Step 3: Sync to GitLab
# ============================================
echo -e "${BLUE}[3/5] Syncing to GitLab (stoa-gitops)...${NC}"

if [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}DRY RUN: Would sync the following files:${NC}"
  find "$TEMP_DIR" -name "*.yaml" -exec echo "  - {}" \;
else
  if [ -z "$GITLAB_TOKEN" ]; then
    echo -e "${YELLOW}GITLAB_TOKEN not set, skipping GitLab sync${NC}"
    echo "Set GITLAB_TOKEN to enable automatic sync"
  else
    GITLAB_PROJECT="${GITLAB_PROJECT:-cab6961310/stoa-gitops}"
    GITLAB_REPO_DIR=$(mktemp -d)

    git clone "https://oauth2:${GITLAB_TOKEN}@gitlab.com/${GITLAB_PROJECT}.git" "$GITLAB_REPO_DIR" 2>/dev/null

    # Copy configs
    mkdir -p "$GITLAB_REPO_DIR/webmethods/apis"
    mkdir -p "$GITLAB_REPO_DIR/webmethods/policies"
    mkdir -p "$GITLAB_REPO_DIR/platform/applications"
    mkdir -p "$GITLAB_REPO_DIR/platform/scopes"

    cp "$TEMP_DIR/apis/"*.yaml "$GITLAB_REPO_DIR/webmethods/apis/" 2>/dev/null || true
    cp "$TEMP_DIR/policies/"*.yaml "$GITLAB_REPO_DIR/webmethods/policies/" 2>/dev/null || true
    cp "$TEMP_DIR/applications/"*.yaml "$GITLAB_REPO_DIR/platform/applications/" 2>/dev/null || true
    cp "$TEMP_DIR/scopes/"*.yaml "$GITLAB_REPO_DIR/platform/scopes/" 2>/dev/null || true

    cd "$GITLAB_REPO_DIR"
    git add -A
    if ! git diff --staged --quiet; then
      git commit -m "bootstrap: platform configs from init script (env: $ENV)"
      git push origin main
      echo -e "${GREEN}✓ Synced to GitLab${NC}"
    else
      echo -e "${YELLOW}No changes to sync${NC}"
    fi

    rm -rf "$GITLAB_REPO_DIR"
    cd "$PROJECT_ROOT"
  fi
fi
echo ""

# ============================================
# Step 4: Trigger Gateway Reconciliation
# ============================================
echo -e "${BLUE}[4/5] Triggering Gateway reconciliation...${NC}"

if [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}DRY RUN: Would trigger AWX job 'reconcile-webmethods'${NC}"
else
  if [ -z "$AWX_TOKEN" ]; then
    echo -e "${YELLOW}AWX_TOKEN not set, skipping AWX trigger${NC}"
    echo "Gateway will sync on next ArgoCD reconciliation"
  else
    AWX_URL="${AWX_URL:-https://awx.${BASE_DOMAIN}}"

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
      "${AWX_URL}/api/v2/job_templates/reconcile-webmethods/launch/" \
      -H "Authorization: Bearer ${AWX_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"extra_vars\": {\"env\": \"$ENV\"}}" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" = "201" ]; then
      JOB_ID=$(echo "$RESPONSE" | head -n-1 | jq -r '.id')
      echo -e "${GREEN}✓ AWX job triggered: $JOB_ID${NC}"

      echo "Waiting for job completion..."
      for i in {1..30}; do
        STATUS=$(curl -s "${AWX_URL}/api/v2/jobs/${JOB_ID}/" \
          -H "Authorization: Bearer ${AWX_TOKEN}" | jq -r '.status')

        case "$STATUS" in
          successful)
            echo -e "${GREEN}✓ Reconciliation successful${NC}"
            break
            ;;
          failed|error)
            echo -e "${RED}✗ Reconciliation failed${NC}"
            break
            ;;
          *)
            echo "  Status: $STATUS..."
            sleep 10
            ;;
        esac
      done
    else
      echo -e "${YELLOW}AWX trigger returned HTTP $HTTP_CODE${NC}"
    fi
  fi
fi
echo ""

# ============================================
# Step 5: Verify Deployment
# ============================================
echo -e "${BLUE}[5/5] Verifying deployment...${NC}"

if [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}DRY RUN: Would verify endpoints${NC}"
else
  echo "Checking Control-Plane-API on Gateway..."
  sleep 5

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://apis.${BASE_DOMAIN}/gateway/Control-Plane-API/2.0/" 2>/dev/null || echo "000")

  case "$HTTP_CODE" in
    200|401|403)
      echo -e "${GREEN}✓ Control-Plane-API accessible on Gateway (HTTP $HTTP_CODE)${NC}"
      ;;
    404)
      echo -e "${YELLOW}⚠ Control-Plane-API not yet deployed on Gateway${NC}"
      echo "  Run 'kubectl apply' or wait for ArgoCD sync"
      ;;
    000)
      echo -e "${YELLOW}⚠ Could not reach Gateway${NC}"
      ;;
    *)
      echo -e "${YELLOW}⚠ Unexpected response: HTTP $HTTP_CODE${NC}"
      ;;
  esac

  echo ""
  echo "Checking backend services..."
  curl -s "https://api.${BASE_DOMAIN}/health/ready" 2>/dev/null | jq . || echo "Backend not reachable"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}        Platform Bootstrap Complete!                       ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Verify configs in GitLab: https://gitlab.com/cab6961310/stoa-gitops"
echo "  2. Check ArgoCD sync status: https://argocd.${BASE_DOMAIN}"
echo "  3. Verify Gateway APIs: https://gateway.${BASE_DOMAIN}"
echo ""
