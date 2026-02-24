#!/usr/bin/env bash
# =============================================================================
# catalog-sync.sh — Drift detection: platform-catalog.yaml vs K8s live state
# =============================================================================
# Compares declared services in docs/platform-catalog.yaml against actual
# K8s deployments. Reports missing, extra, or mismatched services.
#
# Usage:
#   ./scripts/ops/catalog-sync.sh                  # Full check
#   ./scripts/ops/catalog-sync.sh --json           # JSON output
#   ./scripts/ops/catalog-sync.sh --ci             # Exit 1 on drift (CI mode)
#
# Requirements: kubectl, yq (https://github.com/mikefarah/yq)
# =============================================================================

set -euo pipefail

CATALOG_FILE="${CATALOG_FILE:-docs/platform-catalog.yaml}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CATALOG_PATH="$REPO_ROOT/$CATALOG_FILE"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

MODE="text"
CI_MODE=false
DRIFT_COUNT=0
WARNINGS=()
ERRORS=()

# Parse args
for arg in "$@"; do
  case $arg in
    --json)  MODE="json" ;;
    --ci)    CI_MODE=true ;;
    --help)
      echo "Usage: $0 [--json] [--ci]"
      echo "  --json   Output as JSON"
      echo "  --ci     Exit 1 on any drift (for CI pipelines)"
      exit 0
      ;;
  esac
done

# Check prerequisites
if ! command -v yq &>/dev/null; then
  echo "Error: yq is required. Install: brew install yq" >&2
  exit 1
fi

if [ ! -f "$CATALOG_PATH" ]; then
  echo "Error: Catalog not found at $CATALOG_PATH" >&2
  exit 1
fi

# Check if kubectl is available and cluster is reachable
KUBECTL_AVAILABLE=false
if command -v kubectl &>/dev/null; then
  if kubectl cluster-info &>/dev/null 2>&1; then
    KUBECTL_AVAILABLE=true
  fi
fi

log_ok() {
  if [ "$MODE" = "text" ]; then
    echo -e "  ${GREEN}OK${NC}  $1"
  fi
}

log_warn() {
  WARNINGS+=("$1")
  if [ "$MODE" = "text" ]; then
    echo -e "  ${YELLOW}WARN${NC}  $1"
  fi
}

log_error() {
  ERRORS+=("$1")
  DRIFT_COUNT=$((DRIFT_COUNT + 1))
  if [ "$MODE" = "text" ]; then
    echo -e "  ${RED}DRIFT${NC}  $1"
  fi
}

log_info() {
  if [ "$MODE" = "text" ]; then
    echo -e "  ${BLUE}INFO${NC}  $1"
  fi
}

# =============================================================================
# Step 1: Validate catalog YAML structure
# =============================================================================
validate_catalog() {
  if [ "$MODE" = "text" ]; then
    echo -e "\n${BLUE}[1/4] Validating catalog structure${NC}"
  fi

  # Check apiVersion
  API_VERSION=$(yq '.apiVersion' "$CATALOG_PATH")
  if [ "$API_VERSION" != "v1" ]; then
    log_error "apiVersion is '$API_VERSION', expected 'v1'"
  else
    log_ok "apiVersion: v1"
  fi

  # Check kind
  KIND=$(yq '.kind' "$CATALOG_PATH")
  if [ "$KIND" != "PlatformCatalog" ]; then
    log_error "kind is '$KIND', expected 'PlatformCatalog'"
  else
    log_ok "kind: PlatformCatalog"
  fi

  # Count services
  SERVICE_COUNT=$(yq '.services | length' "$CATALOG_PATH")
  if [ "$SERVICE_COUNT" -eq 0 ]; then
    log_error "No services declared in catalog"
  else
    log_ok "$SERVICE_COUNT services declared"
  fi

  # Check for sensitive data (IPs, tokens)
  if grep -qE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' "$CATALOG_PATH"; then
    log_error "Catalog contains IP addresses — use logical names only"
  else
    log_ok "No IP addresses found (good)"
  fi

  if grep -qiE '(token|password|secret|key):\s*["\x27]?[A-Za-z0-9+/=]{8,}' "$CATALOG_PATH"; then
    log_error "Catalog may contain hardcoded secrets"
  else
    log_ok "No hardcoded secrets detected"
  fi
}

# =============================================================================
# Step 2: Check K8s deployments vs catalog (if kubectl available)
# =============================================================================
check_k8s_drift() {
  if [ "$MODE" = "text" ]; then
    echo -e "\n${BLUE}[2/4] Checking K8s deployments vs catalog${NC}"
  fi

  if [ "$KUBECTL_AVAILABLE" = false ]; then
    log_warn "kubectl not available or cluster unreachable — skipping K8s drift check"
    return
  fi

  # Get all K8s services in catalog that deploy to K8s
  CATALOG_K8S_SERVICES=$(yq -r '.services[] | select(.deploy.prod.cluster == "ovh-mks") | .deploy.prod.k8sName' "$CATALOG_PATH" | sort)

  # Get actual deployments in stoa-system
  LIVE_DEPLOYMENTS=$(kubectl get deployments -n stoa-system -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | sort)

  # Check each catalog service exists in K8s
  while IFS= read -r svc; do
    [ -z "$svc" ] && continue
    [ "$svc" = "null" ] && continue
    if echo "$LIVE_DEPLOYMENTS" | grep -qx "$svc"; then
      # Check replica count
      EXPECTED_REPLICAS=$(yq -r ".services[] | select(.deploy.prod.k8sName == \"$svc\") | .deploy.prod.replicas" "$CATALOG_PATH")
      ACTUAL_REPLICAS=$(kubectl get deployment "$svc" -n stoa-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
      ACTUAL_REPLICAS=${ACTUAL_REPLICAS:-0}

      if [ "$EXPECTED_REPLICAS" != "null" ] && [ "$ACTUAL_REPLICAS" != "$EXPECTED_REPLICAS" ]; then
        log_warn "$svc: replicas $ACTUAL_REPLICAS/$EXPECTED_REPLICAS (expected: $EXPECTED_REPLICAS)"
      else
        log_ok "$svc: running ($ACTUAL_REPLICAS replicas)"
      fi
    else
      log_error "$svc: declared in catalog but NOT found in K8s (stoa-system)"
    fi
  done <<< "$CATALOG_K8S_SERVICES"

  # Check for undeclared deployments in K8s
  while IFS= read -r deploy; do
    [ -z "$deploy" ] && continue
    if ! echo "$CATALOG_K8S_SERVICES" | grep -qx "$deploy"; then
      log_warn "$deploy: running in K8s but NOT declared in catalog"
    fi
  done <<< "$LIVE_DEPLOYMENTS"

  # Also check monitoring namespace
  MONITORING_DEPLOYMENTS=$(kubectl get deployments -n monitoring -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | sort)
  CATALOG_MONITORING=$(yq -r '.services[] | select(.deploy.prod.namespace == "monitoring") | .deploy.prod.k8sName' "$CATALOG_PATH" | sort)

  while IFS= read -r svc; do
    [ -z "$svc" ] && continue
    [ "$svc" = "null" ] && continue
    if echo "$MONITORING_DEPLOYMENTS" | grep -q "$svc"; then
      log_ok "$svc: running in monitoring namespace"
    else
      log_warn "$svc: declared for monitoring namespace but not found (may be StatefulSet)"
    fi
  done <<< "$CATALOG_MONITORING"
}

# =============================================================================
# Step 3: Check dependency graph consistency
# =============================================================================
check_dependencies() {
  if [ "$MODE" = "text" ]; then
    echo -e "\n${BLUE}[3/4] Checking dependency graph consistency${NC}"
  fi

  SERVICE_NAMES=$(yq -r '.services[].name' "$CATALOG_PATH")

  while IFS= read -r svc; do
    [ -z "$svc" ] && continue
    DEPS=$(yq -r ".services[] | select(.name == \"$svc\") | .dependsOn[]?" "$CATALOG_PATH" 2>/dev/null)
    while IFS= read -r dep; do
      [ -z "$dep" ] && continue
      if ! echo "$SERVICE_NAMES" | grep -qx "$dep"; then
        log_error "$svc depends on '$dep' which is NOT declared in catalog"
      fi
    done <<< "$DEPS"
  done <<< "$SERVICE_NAMES"

  # Check for circular dependencies (simple 2-hop check)
  while IFS= read -r svc; do
    [ -z "$svc" ] && continue
    DEPS=$(yq -r ".services[] | select(.name == \"$svc\") | .dependsOn[]?" "$CATALOG_PATH" 2>/dev/null)
    while IFS= read -r dep; do
      [ -z "$dep" ] && continue
      REVERSE_DEPS=$(yq -r ".services[] | select(.name == \"$dep\") | .dependsOn[]?" "$CATALOG_PATH" 2>/dev/null)
      if echo "$REVERSE_DEPS" | grep -qx "$svc"; then
        log_warn "Circular dependency: $svc <-> $dep"
      fi
    done <<< "$DEPS"
  done <<< "$SERVICE_NAMES"

  log_ok "Dependency graph validated"
}

# =============================================================================
# Step 4: Summary
# =============================================================================
print_summary() {
  if [ "$MODE" = "text" ]; then
    echo -e "\n${BLUE}[4/4] Summary${NC}"
    echo "  Services: $(yq '.services | length' "$CATALOG_PATH")"
    echo "  Clusters: $(yq '.clusters | length' "$CATALOG_PATH")"
    echo "  Roles: $(yq '.roles | length' "$CATALOG_PATH")"
    echo "  Drifts: $DRIFT_COUNT"
    echo "  Warnings: ${#WARNINGS[@]}"

    if [ "$DRIFT_COUNT" -eq 0 ]; then
      echo -e "\n  ${GREEN}No drift detected.${NC}"
    else
      echo -e "\n  ${RED}$DRIFT_COUNT drift(s) detected!${NC}"
    fi
  fi

  if [ "$MODE" = "json" ]; then
    # Build JSON output
    ERRORS_JSON="["
    for i in "${!ERRORS[@]}"; do
      [ "$i" -gt 0 ] && ERRORS_JSON+=","
      ERRORS_JSON+="\"${ERRORS[$i]}\""
    done
    ERRORS_JSON+="]"

    WARNINGS_JSON="["
    for i in "${!WARNINGS[@]}"; do
      [ "$i" -gt 0 ] && WARNINGS_JSON+=","
      WARNINGS_JSON+="\"${WARNINGS[$i]}\""
    done
    WARNINGS_JSON+="]"

    cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "services": $(yq '.services | length' "$CATALOG_PATH"),
  "clusters": $(yq '.clusters | length' "$CATALOG_PATH"),
  "drifts": $DRIFT_COUNT,
  "warnings": ${#WARNINGS[@]},
  "errors": $ERRORS_JSON,
  "warning_details": $WARNINGS_JSON
}
EOF
  fi
}

# =============================================================================
# Main
# =============================================================================
if [ "$MODE" = "text" ]; then
  echo -e "${BLUE}Platform Catalog Sync — Drift Detection${NC}"
  echo "  Catalog: $CATALOG_FILE"
  echo "  kubectl: $([ "$KUBECTL_AVAILABLE" = true ] && echo "connected" || echo "unavailable")"
fi

validate_catalog
check_k8s_drift
check_dependencies
print_summary

if [ "$CI_MODE" = true ] && [ "$DRIFT_COUNT" -gt 0 ]; then
  exit 1
fi
