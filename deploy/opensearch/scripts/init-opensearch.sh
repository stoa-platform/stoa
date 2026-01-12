#!/bin/bash
# =============================================================================
# STOA Platform - OpenSearch Initialization Script
# =============================================================================
# Applies index templates and ISM policies to OpenSearch cluster
#
# Usage:
#   ./init-opensearch.sh [OPTIONS]
#
# Options:
#   --host        OpenSearch host (default: https://opensearch.stoa.cab-i.com)
#   --user        Admin username (default: admin)
#   --password    Admin password (from env OPENSEARCH_PASSWORD or prompt)
#   --dry-run     Show what would be done without executing
#   --force       Overwrite existing templates/policies
#
# =============================================================================

set -euo pipefail

# Defaults
OPENSEARCH_HOST="${OPENSEARCH_HOST:-https://opensearch.stoa.cab-i.com}"
OPENSEARCH_USER="${OPENSEARCH_USER:-admin}"
OPENSEARCH_PASSWORD="${OPENSEARCH_PASSWORD:-}"
DRY_RUN=false
FORCE=false

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="${SCRIPT_DIR}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --host) OPENSEARCH_HOST="$2"; shift 2 ;;
    --user) OPENSEARCH_USER="$2"; shift 2 ;;
    --password) OPENSEARCH_PASSWORD="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --force) FORCE=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--host URL] [--user USER] [--password PASS] [--dry-run] [--force]"
      exit 0
      ;;
    *) log_error "Unknown option: $1"; exit 1 ;;
  esac
done

# Prompt for password if not set
if [[ -z "$OPENSEARCH_PASSWORD" ]]; then
  read -s -p "Enter OpenSearch admin password: " OPENSEARCH_PASSWORD
  echo
fi

# Build curl auth
CURL_AUTH="-u ${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}"
CURL_OPTS="-s -k"

# Test connection
log_info "Testing connection to ${OPENSEARCH_HOST}..."
if ! curl ${CURL_OPTS} ${CURL_AUTH} "${OPENSEARCH_HOST}/_cluster/health" > /dev/null 2>&1; then
  log_error "Cannot connect to OpenSearch at ${OPENSEARCH_HOST}"
  exit 1
fi
log_success "Connected to OpenSearch cluster"

# Get cluster info
CLUSTER_INFO=$(curl ${CURL_OPTS} ${CURL_AUTH} "${OPENSEARCH_HOST}/")
CLUSTER_NAME=$(echo "$CLUSTER_INFO" | jq -r '.cluster_name // "unknown"')
VERSION=$(echo "$CLUSTER_INFO" | jq -r '.version.number // "unknown"')
log_info "Cluster: ${CLUSTER_NAME}, Version: ${VERSION}"

# Function to apply index template
apply_template() {
  local template_file="$1"
  local template_name=$(basename "$template_file" .json | sed 's/-template//')
  
  log_info "Applying index template: ${template_name}"
  
  if [[ "$DRY_RUN" == "true" ]]; then
    log_warning "[DRY-RUN] Would apply template from ${template_file}"
    return 0
  fi
  
  # Check if template exists
  local exists=$(curl ${CURL_OPTS} ${CURL_AUTH} -o /dev/null -w "%{http_code}" \
    "${OPENSEARCH_HOST}/_index_template/${template_name}")
  
  if [[ "$exists" == "200" && "$FORCE" != "true" ]]; then
    log_warning "Template '${template_name}' already exists (use --force to overwrite)"
    return 0
  fi
  
  # Apply template
  local response=$(curl ${CURL_OPTS} ${CURL_AUTH} -X PUT \
    -H "Content-Type: application/json" \
    -d "@${template_file}" \
    "${OPENSEARCH_HOST}/_index_template/${template_name}")
  
  if echo "$response" | jq -e '.acknowledged == true' > /dev/null 2>&1; then
    log_success "Template '${template_name}' applied successfully"
  else
    log_error "Failed to apply template '${template_name}': ${response}"
    return 1
  fi
}

# Function to apply ISM policy
apply_ism_policy() {
  local policy_id="$1"
  local policy_json="$2"
  
  log_info "Applying ISM policy: ${policy_id}"
  
  if [[ "$DRY_RUN" == "true" ]]; then
    log_warning "[DRY-RUN] Would apply ISM policy ${policy_id}"
    return 0
  fi
  
  # Check if policy exists
  local exists=$(curl ${CURL_OPTS} ${CURL_AUTH} -o /dev/null -w "%{http_code}" \
    "${OPENSEARCH_HOST}/_plugins/_ism/policies/${policy_id}")
  
  if [[ "$exists" == "200" && "$FORCE" != "true" ]]; then
    log_warning "ISM policy '${policy_id}' already exists (use --force to overwrite)"
    return 0
  fi
  
  # Apply policy
  local method="PUT"
  if [[ "$exists" == "200" ]]; then
    # Get current seq_no and primary_term for update
    local current=$(curl ${CURL_OPTS} ${CURL_AUTH} "${OPENSEARCH_HOST}/_plugins/_ism/policies/${policy_id}")
    local seq_no=$(echo "$current" | jq -r '._seq_no')
    local primary_term=$(echo "$current" | jq -r '._primary_term')
    local url="${OPENSEARCH_HOST}/_plugins/_ism/policies/${policy_id}?if_seq_no=${seq_no}&if_primary_term=${primary_term}"
  else
    local url="${OPENSEARCH_HOST}/_plugins/_ism/policies/${policy_id}"
  fi
  
  local response=$(curl ${CURL_OPTS} ${CURL_AUTH} -X PUT \
    -H "Content-Type: application/json" \
    -d "${policy_json}" \
    "${url}")
  
  if echo "$response" | jq -e '._id' > /dev/null 2>&1; then
    log_success "ISM policy '${policy_id}' applied successfully"
  else
    log_error "Failed to apply ISM policy '${policy_id}': ${response}"
    return 1
  fi
}

# Function to create initial index with alias
create_initial_index() {
  local alias_name="$1"
  local index_name="${alias_name}-000001"
  
  log_info "Creating initial index: ${index_name} with alias ${alias_name}"
  
  if [[ "$DRY_RUN" == "true" ]]; then
    log_warning "[DRY-RUN] Would create index ${index_name}"
    return 0
  fi
  
  # Check if alias exists
  local exists=$(curl ${CURL_OPTS} ${CURL_AUTH} -o /dev/null -w "%{http_code}" \
    "${OPENSEARCH_HOST}/_alias/${alias_name}")
  
  if [[ "$exists" == "200" ]]; then
    log_warning "Alias '${alias_name}' already exists"
    return 0
  fi
  
  # Create index with write alias
  local response=$(curl ${CURL_OPTS} ${CURL_AUTH} -X PUT \
    -H "Content-Type: application/json" \
    -d "{\"aliases\": {\"${alias_name}\": {\"is_write_index\": true}}}" \
    "${OPENSEARCH_HOST}/${index_name}")
  
  if echo "$response" | jq -e '.acknowledged == true' > /dev/null 2>&1; then
    log_success "Index '${index_name}' created with alias '${alias_name}'"
  else
    log_error "Failed to create index '${index_name}': ${response}"
    return 1
  fi
}

# Main execution
echo "=============================================="
echo "  STOA OpenSearch Initialization"
echo "=============================================="
echo ""

# 1. Apply index templates
log_info "=== Step 1: Index Templates ==="
for template_file in "${TEMPLATES_DIR}"/tools-template.json \
                     "${TEMPLATES_DIR}"/audit-template.json \
                     "${TEMPLATES_DIR}"/analytics-template.json; do
  if [[ -f "$template_file" ]]; then
    apply_template "$template_file"
  else
    log_warning "Template file not found: ${template_file}"
  fi
done

# 2. Apply ISM policies
log_info "=== Step 2: ISM Policies ==="
if [[ -f "${TEMPLATES_DIR}/ism-policies.json" ]]; then
  # Extract and apply each policy
  policies=$(cat "${TEMPLATES_DIR}/ism-policies.json" | jq -c '.policies[]')
  while IFS= read -r policy; do
    policy_id=$(echo "$policy" | jq -r '.policy_id')
    policy_body=$(echo "$policy" | jq -c '{policy: del(.policy_id, .ism_template) | . + {ism_template: .ism_template}}' | jq -c '{policy: .policy}')
    apply_ism_policy "$policy_id" "$policy_body"
  done <<< "$policies"
else
  log_warning "ISM policies file not found"
fi

# 3. Create initial indices with aliases
log_info "=== Step 3: Initial Indices ==="
create_initial_index "audit"
create_initial_index "analytics"

# 4. Create tools index (not rolled over, single index)
log_info "Creating tools index..."
if [[ "$DRY_RUN" != "true" ]]; then
  exists=$(curl ${CURL_OPTS} ${CURL_AUTH} -o /dev/null -w "%{http_code}" \
    "${OPENSEARCH_HOST}/tools")
  if [[ "$exists" != "200" ]]; then
    response=$(curl ${CURL_OPTS} ${CURL_AUTH} -X PUT \
      "${OPENSEARCH_HOST}/tools")
    if echo "$response" | jq -e '.acknowledged == true' > /dev/null 2>&1; then
      log_success "Index 'tools' created"
    fi
  else
    log_warning "Index 'tools' already exists"
  fi
fi

# Summary
echo ""
echo "=============================================="
log_success "OpenSearch initialization complete!"
echo "=============================================="
echo ""
echo "Indices created:"
echo "  - tools          (permanent, catalog)"
echo "  - audit-*        (1 year retention)"
echo "  - analytics-*    (90 days retention)"
echo ""
echo "Next steps:"
echo "  1. Start the sync service to populate tools catalog"
echo "  2. Configure audit middleware in FastAPI"
echo "  3. Import Kibana dashboards"
