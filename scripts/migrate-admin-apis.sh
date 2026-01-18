#!/bin/bash
# migrate-admin-apis.sh
# Migrate admin APIs from stoa-gitops/webmethods to stoa-catalog/tenants/stoa-platform
#
# Usage:
#   ./migrate-admin-apis.sh --gitops-dir=/path/to/stoa-gitops --catalog-dir=/path/to/stoa-catalog
#   ./migrate-admin-apis.sh --dry-run  # Simulate without changes

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DRY_RUN=false
GITOPS_DIR=""
CATALOG_DIR=""
STOA_PLATFORM_TENANT="stoa-platform"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --gitops-dir=*)
            GITOPS_DIR="${1#*=}"
            shift
            ;;
        --catalog-dir=*)
            CATALOG_DIR="${1#*=}"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --gitops-dir=PATH   Path to stoa-gitops repository"
            echo "  --catalog-dir=PATH  Path to stoa-catalog repository"
            echo "  --dry-run           Simulate without making changes"
            echo "  -h, --help          Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validation
if [[ -z "$GITOPS_DIR" ]]; then
    echo -e "${RED}Error: --gitops-dir is required${NC}"
    exit 1
fi

if [[ -z "$CATALOG_DIR" ]]; then
    echo -e "${RED}Error: --catalog-dir is required${NC}"
    exit 1
fi

if [[ ! -d "$GITOPS_DIR" ]]; then
    echo -e "${RED}Error: GitOps directory not found: $GITOPS_DIR${NC}"
    exit 1
fi

if [[ ! -d "$CATALOG_DIR" ]]; then
    echo -e "${RED}Error: Catalog directory not found: $CATALOG_DIR${NC}"
    exit 1
fi

# Paths
WEBMETHODS_DIR="$GITOPS_DIR/webmethods"
TENANTS_DIR="$CATALOG_DIR/tenants"
TARGET_DIR="$TENANTS_DIR/$STOA_PLATFORM_TENANT"

echo -e "${BLUE}=== STOA Admin APIs Migration ===${NC}"
echo ""
echo "Source: $WEBMETHODS_DIR/apis"
echo "Target: $TARGET_DIR/apis"
echo "Dry-run: $DRY_RUN"
echo ""

# Check source directory
if [[ ! -d "$WEBMETHODS_DIR/apis" ]]; then
    echo -e "${YELLOW}Warning: No APIs found in $WEBMETHODS_DIR/apis${NC}"
    exit 0
fi

# Count APIs to migrate
API_COUNT=$(find "$WEBMETHODS_DIR/apis" -name "*.yaml" -o -name "*.yml" 2>/dev/null | wc -l | tr -d ' ')
echo -e "${BLUE}Found $API_COUNT API(s) to migrate${NC}"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}=== DRY-RUN MODE - No changes will be made ===${NC}"
    echo ""
fi

# Create target directories
echo -e "${BLUE}Step 1: Creating target directories${NC}"
if [[ "$DRY_RUN" == "false" ]]; then
    mkdir -p "$TARGET_DIR/apis"
    echo -e "${GREEN}  Created: $TARGET_DIR/apis${NC}"
else
    echo -e "${YELLOW}  Would create: $TARGET_DIR/apis${NC}"
fi

# Create tenant.yaml for stoa-platform
echo ""
echo -e "${BLUE}Step 2: Creating stoa-platform tenant.yaml${NC}"
TENANT_YAML="$TARGET_DIR/tenant.yaml"

TENANT_CONTENT='apiVersion: stoa.io/v1
kind: Tenant
metadata:
  name: stoa-platform
  displayName: "STOA Platform"
  description: "Internal platform APIs - Control Plane and administrative services"
  labels:
    tier: platform
    visibility: internal
    managed-by: gitops

spec:
  portalVisibility: internal

  visibility:
    allowedRoles:
      - platform-admin
      - stoa-operator
      - cpi-admin
    denyRoles:
      - developer
      - api-consumer
      - external-partner

  defaultPolicies:
    - name: require-internal-jwt
    - name: rate-limit-high
      config:
        requestsPerMinute: 1000
    - name: audit-all-requests

  settings:
    max_apis: 50
    max_applications: 10
    environments:
      - dev
      - staging
      - prod

  tags:
    - platform
    - internal
    - admin

  contact:
    team: "STOA Platform Team"
    email: "platform@stoa.cab-i.com"
'

if [[ "$DRY_RUN" == "false" ]]; then
    echo "$TENANT_CONTENT" > "$TENANT_YAML"
    echo -e "${GREEN}  Created: $TENANT_YAML${NC}"
else
    echo -e "${YELLOW}  Would create: $TENANT_YAML${NC}"
fi

# Migrate each API
echo ""
echo -e "${BLUE}Step 3: Migrating APIs${NC}"

for api_file in "$WEBMETHODS_DIR/apis"/*.yaml "$WEBMETHODS_DIR/apis"/*.yml; do
    [[ -f "$api_file" ]] || continue

    # Extract API name from filename (without extension)
    api_name=$(basename "$api_file" | sed 's/\.[^.]*$//')

    # Create API directory structure
    api_target_dir="$TARGET_DIR/apis/$api_name"
    api_target_file="$api_target_dir/api.yaml"

    echo -e "  Migrating: $api_name"

    if [[ "$DRY_RUN" == "false" ]]; then
        mkdir -p "$api_target_dir"

        # Convert the API format if needed (add metadata wrapper)
        # Read original content
        original_content=$(cat "$api_file")

        # Check if it already has apiVersion (new format)
        if echo "$original_content" | grep -q "^apiVersion:"; then
            # Already in new format, just copy
            cp "$api_file" "$api_target_file"
        else
            # Old format, wrap in new structure
            cat > "$api_target_file" << EOF
apiVersion: stoa.cab-i.com/v1
kind: API
metadata:
  name: $api_name
  version: "1.0"
  labels:
    managed-by: gitops
    migrated-from: stoa-gitops

spec:
  displayName: $api_name
  description: "Migrated from stoa-gitops/webmethods/apis"
  status: published
  category: platform

  tags:
    - platform
    - internal
    - migrated

# Original content below (may need manual adjustment)
# ---
$(cat "$api_file" | sed 's/^/# /')
EOF
        fi

        echo -e "${GREEN}    -> $api_target_file${NC}"
    else
        echo -e "${YELLOW}    Would create: $api_target_dir/api.yaml${NC}"
    fi
done

# Create deprecation notice in old location
echo ""
echo -e "${BLUE}Step 4: Creating deprecation notice${NC}"
DEPRECATED_README="$WEBMETHODS_DIR/apis/DEPRECATED.md"

DEPRECATED_CONTENT="# DEPRECATED

> **Warning**: This directory is deprecated. APIs have been migrated to stoa-catalog.

## New Location

All APIs are now managed in the unified tenant structure:

\`\`\`
stoa-catalog/tenants/stoa-platform/apis/
\`\`\`

## Migration Date

$(date -u +"%Y-%m-%dT%H:%M:%SZ")

## What Changed

1. Admin APIs moved from \`stoa-gitops/webmethods/apis/\` to \`stoa-catalog/tenants/stoa-platform/apis/\`
2. New \`tenant.yaml\` with \`portalVisibility: internal\` controls portal visibility
3. Single source of truth: \`stoa-catalog\` repository

## ArgoCD

The ArgoCD application \`stoa-webmethods-gitops\` now points to \`stoa-catalog\` only.

## Rollback

If needed, revert the ArgoCD application to use multi-source configuration.
"

if [[ "$DRY_RUN" == "false" ]]; then
    echo "$DEPRECATED_CONTENT" > "$DEPRECATED_README"
    echo -e "${GREEN}  Created: $DEPRECATED_README${NC}"
else
    echo -e "${YELLOW}  Would create: $DEPRECATED_README${NC}"
fi

# Summary
echo ""
echo -e "${BLUE}=== Migration Summary ===${NC}"
echo ""
echo "APIs migrated: $API_COUNT"
echo "Source: $WEBMETHODS_DIR/apis"
echo "Target: $TARGET_DIR/apis"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}DRY-RUN complete. No changes were made.${NC}"
    echo ""
    echo "To apply changes, run without --dry-run:"
    echo "  $0 --gitops-dir=$GITOPS_DIR --catalog-dir=$CATALOG_DIR"
else
    echo -e "${GREEN}Migration complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Review migrated files in $TARGET_DIR"
    echo "2. Commit changes to stoa-catalog repository"
    echo "3. Update ArgoCD application to use single source"
    echo "4. Test reconciliation: ansible-playbook reconcile-webmethods.yml -e env=dev --check"
fi
