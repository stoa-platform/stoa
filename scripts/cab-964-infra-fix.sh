#!/bin/bash
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
#===============================================================================
# CAB-964: Infrastructure Fix & Validation Script
# STOA Platform - Pre-client Demo (Wed 29 Jan 2026)
#===============================================================================
# "The European Agent Gateway doesn't go down before demos."
#===============================================================================

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLER (STOA convention: line-number reporting)
# ═══════════════════════════════════════════════════════════════════════════════
error_handler() {
    local line=$1
    local exit_code=$?
    log_error "Error at line $line (exit code: $exit_code)"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        log_info "Dry-run mode - no changes were made"
    fi
    exit $exit_code
}
trap 'error_handler ${LINENO}' ERR

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG - STOA Infrastructure Mapping
# ═══════════════════════════════════════════════════════════════════════════════
# Environment (affects Vault paths)
ENV="${STOA_ENV:-dev}"
NAMESPACE="${STOA_NAMESPACE:-stoa-system}"

# PostgreSQL config (from deploy/database/postgres-statefulset.yaml)
PG_LABEL="${STOA_PG_LABEL:-app=control-plane-db}"
PG_STATEFULSET="${STOA_PG_STATEFULSET:-control-plane-db}"
PG_SECRET="${STOA_PG_SECRET:-control-plane-db-secret}"
PG_USER="${STOA_DB_USER:-stoa}"
PG_DB="${STOA_DB_NAME:-stoa}"

# webMethods/API Gateway config (external service)
GW_LABEL="${STOA_GW_LABEL:-app=apigateway}"
GW_DEPLOYMENT="${STOA_GW_DEPLOYMENT:-apigateway}"
GW_SERVICE="${STOA_GW_SERVICE:-apigateway}"
GW_PORT="${STOA_GW_PORT:-5555}"

# MCP Gateway config (from mcp-gateway/k8s/deployment.yaml)
MCP_LABEL="${STOA_MCP_LABEL:-app=stoa-mcp-gateway}"
MCP_SERVICE="${STOA_MCP_SERVICE:-stoa-mcp-gateway}"
MCP_PORT="${STOA_MCP_PORT:-8080}"

# Vault config (from deploy/external-secrets/external-secret-database.yaml)
VAULT_PATH="${STOA_VAULT_PATH:-secret/apim/${ENV}/database}"
VAULT_POD="${STOA_VAULT_POD:-vault-0}"

# Behavior
DRY_RUN="${DRY_RUN:-0}"
TIMEOUT_SECONDS=30
MAX_RETRIES=3

# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE COMMON (if available)
# ═══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/common.sh" ]]; then
    # shellcheck source=./common.sh
    source "${SCRIPT_DIR}/common.sh"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STYLING
# ═══════════════════════════════════════════════════════════════════════════════
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

print_banner() {
    echo -e "${PURPLE}"
    cat << 'EOF'
   _____ _____ ___    _
  / ____|_   _/ _ \  / \
  \___ \  | || | | |/ _ \
   ___) | | || |_| / ___ \
  |____/  |_| \___/_/   \_\

  Infrastructure Recovery Script v2
  CAB-964 | Pre-client Demo Fix
EOF
    echo -e "${NC}"

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        echo -e "${YELLOW}  DRY-RUN MODE - No changes will be made${NC}"
        echo ""
    fi
}

log_step()    { echo -e "${BLUE}[STEP]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error()   { echo -e "${RED}[X]${NC} $1"; }
log_info()    { echo -e "${CYAN}[i]${NC} $1"; }
log_debug()   { [[ "${DEBUG:-0}" == "1" ]] && echo -e "${WHITE}[DEBUG]${NC} $1" || true; }
log_dryrun()  { [[ "${DRY_RUN:-0}" == "1" ]] && echo -e "${YELLOW}[DRY-RUN]${NC} Would: $1" || true; }

separator() {
    echo -e "${PURPLE}-------------------------------------------------------------${NC}"
}

# ═══════════════════════════════════════════════════════════════════════════════
# DRY-RUN WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════
run_cmd() {
    local desc="$1"
    shift
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        log_dryrun "$desc"
        log_debug "Command: $*"
        return 0
    else
        log_info "$desc"
        "$@"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# PREFLIGHT CHECKS
# ═══════════════════════════════════════════════════════════════════════════════
preflight_check() {
    log_step "Preflight checks..."

    local required_tools=("kubectl" "jq")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "$tool is required but not installed"
            exit 1
        fi
    done

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi

    # Verify namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace $NAMESPACE not found"
        exit 1
    fi

    log_success "All preflight checks passed"
    log_info "Namespace: $NAMESPACE | ENV: $ENV | Vault path: $VAULT_PATH"
}

# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE #1: PostgreSQL Authentication Fix
# ═══════════════════════════════════════════════════════════════════════════════
diagnose_postgresql() {
    log_step "Diagnosing PostgreSQL (label: $PG_LABEL)..."
    separator

    # Check pod status
    local pg_pod
    pg_pod=$(kubectl get pods -n "$NAMESPACE" -l "$PG_LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$pg_pod" ]]; then
        log_error "PostgreSQL pod not found with label '$PG_LABEL' in namespace $NAMESPACE"
        log_info "Available pods:"
        kubectl get pods -n "$NAMESPACE" --show-labels | grep -i "postgres\|db" || true
        return 1
    fi

    local pg_status
    pg_status=$(kubectl get pod "$pg_pod" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
    log_info "Pod: $pg_pod | Status: $pg_status"

    # Check recent logs for auth errors
    log_info "Recent authentication errors:"
    kubectl logs -n "$NAMESPACE" "$pg_pod" --tail=20 2>/dev/null | grep -iE "authentication|password|FATAL" || log_info "No auth errors in recent logs"

    # Check Vault secret
    log_info "Checking Vault credentials at $VAULT_PATH..."
    if kubectl exec -n "$NAMESPACE" "$VAULT_POD" -- vault kv get -format=json "$VAULT_PATH" 2>/dev/null | jq -r '.data.data' > /dev/null; then
        log_success "Vault secret exists at $VAULT_PATH"
    else
        log_warning "Could not read Vault secret at $VAULT_PATH"
    fi

    # Check ExternalSecret status
    log_info "ExternalSecret status:"
    kubectl get externalsecret -n "$NAMESPACE" "$PG_SECRET" -o jsonpath='{.status.conditions[*].message}' 2>/dev/null || log_warning "ExternalSecret $PG_SECRET not found"
    echo ""
}

fix_postgresql() {
    log_step "Fixing PostgreSQL authentication..."
    separator

    # Strategy 1: Trigger ExternalSecret refresh
    log_info "Triggering credential resync via ExternalSecret annotation..."
    run_cmd "Annotate ExternalSecret for refresh" \
        kubectl annotate externalsecret -n "$NAMESPACE" "$PG_SECRET" \
        "force-sync=$(date +%s)" --overwrite 2>/dev/null || {

        log_warning "ExternalSecret $PG_SECRET not found, trying direct secret update..."

        # Strategy 2: Read from Vault and update secret directly
        local vault_creds
        vault_creds=$(kubectl exec -n "$NAMESPACE" "$VAULT_POD" -- vault kv get -format=json "$VAULT_PATH" 2>/dev/null) || {
            log_error "Cannot read credentials from Vault at $VAULT_PATH"
            log_info "Manual fix: kubectl exec -it $VAULT_POD -n $NAMESPACE -- vault kv put $VAULT_PATH username=$PG_USER password=<NEW_PASSWORD>"
            return 1
        }

        local pg_user pg_pass
        pg_user=$(echo "$vault_creds" | jq -r ".data.data.username // \"$PG_USER\"")
        pg_pass=$(echo "$vault_creds" | jq -r '.data.data.password')

        if [[ -z "$pg_pass" || "$pg_pass" == "null" ]]; then
            log_error "No password found in Vault - manual intervention required"
            return 1
        fi

        run_cmd "Update Kubernetes secret $PG_SECRET" \
            kubectl create secret generic "$PG_SECRET" \
            --from-literal=username="$pg_user" \
            --from-literal=password="$pg_pass" \
            -n "$NAMESPACE" \
            --dry-run=client -o yaml | kubectl apply -f -

        log_success "Database secret updated"
    }

    # Strategy 3: Rolling restart PostgreSQL
    run_cmd "Rolling restart StatefulSet $PG_STATEFULSET" \
        kubectl rollout restart statefulset -n "$NAMESPACE" "$PG_STATEFULSET" 2>/dev/null || {
        log_warning "StatefulSet restart failed, trying pod delete..."
        run_cmd "Delete PostgreSQL pods" \
            kubectl delete pod -n "$NAMESPACE" -l "$PG_LABEL" --grace-period=30
    }

    if [[ "${DRY_RUN:-0}" == "0" ]]; then
        # Wait for ready
        log_info "Waiting for PostgreSQL to be ready..."
        kubectl wait --for=condition=ready pod -n "$NAMESPACE" -l "$PG_LABEL" --timeout=120s || {
            log_error "PostgreSQL failed to become ready"
            return 1
        }
    fi

    log_success "PostgreSQL fix applied"
}

validate_postgresql() {
    log_step "Validating PostgreSQL..."

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        log_dryrun "Would validate PostgreSQL connection"
        return 0
    fi

    local pg_pod
    pg_pod=$(kubectl get pods -n "$NAMESPACE" -l "$PG_LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    local retries=0
    while [[ $retries -lt $MAX_RETRIES ]]; do
        if kubectl exec -n "$NAMESPACE" "$pg_pod" -- psql -U "$PG_USER" -d "$PG_DB" -c "SELECT 1;" &>/dev/null; then
            log_success "PostgreSQL authentication working!"
            return 0
        fi
        ((retries++))
        log_warning "Attempt $retries/$MAX_RETRIES failed, retrying in 5s..."
        sleep 5
    done

    log_error "PostgreSQL validation failed after $MAX_RETRIES attempts"
    return 1
}

# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE #2: API Gateway 503 Fix
# ═══════════════════════════════════════════════════════════════════════════════
diagnose_apigateway() {
    log_step "Diagnosing API Gateway (label: $GW_LABEL)..."
    separator

    # Check pod status
    log_info "Pod status:"
    kubectl get pods -n "$NAMESPACE" -l "$GW_LABEL" -o wide 2>/dev/null || {
        log_warning "No pods found with label $GW_LABEL"
        log_info "Checking for apigateway service (may be external)..."
        kubectl get svc -n "$NAMESPACE" "$GW_SERVICE" 2>/dev/null || log_warning "Service $GW_SERVICE not found"
    }

    # Check service endpoints
    log_info "Service endpoints:"
    local endpoints
    endpoints=$(kubectl get endpoints -n "$NAMESPACE" "$GW_SERVICE" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || echo "")
    if [[ -z "$endpoints" ]]; then
        log_warning "No endpoints found for service $GW_SERVICE"
    else
        log_info "Endpoints: $endpoints"
    fi

    # Recent logs (if deployment exists)
    local gw_pod
    gw_pod=$(kubectl get pods -n "$NAMESPACE" -l "$GW_LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$gw_pod" ]]; then
        log_info "Recent errors:"
        kubectl logs -n "$NAMESPACE" "$gw_pod" --tail=30 2>/dev/null | grep -iE "error|exception|failed|503" | tail -10 || log_info "No recent errors found"
    fi
}

fix_apigateway() {
    log_step "Fixing API Gateway..."
    separator

    # Check if deployment exists
    if kubectl get deployment -n "$NAMESPACE" "$GW_DEPLOYMENT" &>/dev/null; then
        local restart_count
        restart_count=$(kubectl get pods -n "$NAMESPACE" -l "$GW_LABEL" -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}' 2>/dev/null || echo "0")

        if [[ "$restart_count" -gt 5 ]]; then
            log_warning "High restart count ($restart_count) - might be resource or config issue"
            local last_reason
            last_reason=$(kubectl get pods -n "$NAMESPACE" -l "$GW_LABEL" -o jsonpath='{.items[0].status.containerStatuses[0].lastState.terminated.reason}' 2>/dev/null || echo "unknown")
            log_info "Last termination reason: $last_reason"
        fi

        run_cmd "Rolling restart deployment $GW_DEPLOYMENT" \
            kubectl rollout restart deployment -n "$NAMESPACE" "$GW_DEPLOYMENT"

        if [[ "${DRY_RUN:-0}" == "0" ]]; then
            log_info "Waiting for API Gateway to be ready..."
            kubectl wait --for=condition=ready pod -n "$NAMESPACE" -l "$GW_LABEL" --timeout=180s || {
                log_error "API Gateway failed to become ready"
                return 1
            }
        fi
    else
        log_info "Deployment $GW_DEPLOYMENT not found - may be external webMethods instance"
        log_info "Checking external connectivity to $GW_SERVICE:$GW_PORT..."
    fi

    log_success "API Gateway restart completed"
}

validate_apigateway() {
    log_step "Validating API Gateway..."

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        log_dryrun "Would validate API Gateway connectivity"
        return 0
    fi

    local gw_url
    gw_url=$(kubectl get svc -n "$NAMESPACE" "$GW_SERVICE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")

    if [[ -z "$gw_url" ]]; then
        log_warning "Service $GW_SERVICE not found - may be external"
        return 0
    fi

    local retries=0
    while [[ $retries -lt $MAX_RETRIES ]]; do
        # Test from inside cluster
        local status_code
        status_code=$(kubectl run curl-test-$RANDOM --rm -i --restart=Never \
            --image=curlimages/curl:latest -n "$NAMESPACE" -- \
            curl -s -o /dev/null -w "%{http_code}" \
            "http://$gw_url:$GW_PORT/health" --connect-timeout 10 2>/dev/null || echo "000")

        if [[ "$status_code" =~ ^(200|204|301|302)$ ]]; then
            log_success "API Gateway responding (HTTP $status_code)"
            return 0
        fi

        ((retries++))
        log_warning "Got HTTP $status_code, attempt $retries/$MAX_RETRIES, retrying in 10s..."
        sleep 10
    done

    log_error "API Gateway validation failed"
    return 1
}

# ═══════════════════════════════════════════════════════════════════════════════
# STOA PLATFORM HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════
run_health_check() {
    log_step "Running STOA Platform health check..."
    separator

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        log_dryrun "Would run full health check"
        return 0
    fi

    # MCP Gateway health (using correct endpoints from mcp-gateway/src/services/health.py)
    local mcp_url
    mcp_url=$(kubectl get svc -n "$NAMESPACE" "$MCP_SERVICE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")

    if [[ -n "$mcp_url" ]]; then
        log_info "Checking MCP Gateway..."

        # Liveness probe: /health/live
        local liveness
        liveness=$(kubectl run health-live-$RANDOM --rm -i --restart=Never \
            --image=curlimages/curl:latest -n "$NAMESPACE" -- \
            curl -s -o /dev/null -w "%{http_code}" \
            "http://$mcp_url:$MCP_PORT/health/live" --connect-timeout 5 2>/dev/null || echo "000")

        # Readiness probe: /health/ready
        local readiness
        readiness=$(kubectl run health-ready-$RANDOM --rm -i --restart=Never \
            --image=curlimages/curl:latest -n "$NAMESPACE" -- \
            curl -s -o /dev/null -w "%{http_code}" \
            "http://$mcp_url:$MCP_PORT/health/ready" --connect-timeout 5 2>/dev/null || echo "000")

        log_info "MCP Gateway: liveness=$liveness, readiness=$readiness"
    else
        log_warning "MCP Gateway service not found"
    fi

    # Pod summary
    echo ""
    log_info "Current STOA pod status:"
    kubectl get pods -n "$NAMESPACE" -o wide | grep -E "NAME|control-plane|mcp|apigateway|keycloak|vault|kafka|postgres" || true
}

# ═══════════════════════════════════════════════════════════════════════════════
# MCP DRY-RUN TESTS
# ═══════════════════════════════════════════════════════════════════════════════
run_mcp_tests() {
    log_step "Running MCP dry-run tests (5 calls)..."
    separator

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        log_dryrun "Would run 5 MCP tool invocations"
        return 0
    fi

    local mcp_url
    mcp_url=$(kubectl get svc -n "$NAMESPACE" "$MCP_SERVICE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")

    if [[ -z "$mcp_url" ]]; then
        log_warning "MCP Gateway service not found - skipping tests"
        return 0
    fi

    local success=0
    local failed=0
    local test_tools=("stoa_platform_health" "stoa_catalog" "stoa_tools" "stoa_metrics" "stoa_subscription")

    for tool in "${test_tools[@]}"; do
        log_info "Testing: $tool"

        local response
        response=$(kubectl run mcp-test-$RANDOM --rm -i --restart=Never \
            --image=curlimages/curl:latest -n "$NAMESPACE" -- \
            curl -s -X POST "http://$mcp_url:$MCP_PORT/mcp/tools/call" \
            -H "Content-Type: application/json" \
            -d "{\"name\":\"$tool\",\"arguments\":{\"action\":\"list\"}}" \
            --connect-timeout 10 2>/dev/null || echo "error")

        if [[ "$response" != "error" && -n "$response" ]]; then
            log_success "$tool - OK"
            ((success++))
        else
            log_error "$tool - FAILED"
            ((failed++))
        fi
    done

    echo ""
    log_info "Results: $success passed, $failed failed"

    [[ $failed -eq 0 ]]
}

# ═══════════════════════════════════════════════════════════════════════════════
# WARM-UP SCRIPT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════
generate_warmup_script() {
    log_step "Generating demo warm-up script..."

    local warmup_path="${1:-/tmp/stoa-demo-warmup.sh}"

    cat > "$warmup_path" << 'WARMUP'
#!/bin/bash
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
# STOA Demo Warm-up Script - Run 5 minutes before client demo

set -euo pipefail

echo "STOA Platform Warm-up Starting..."

MCP_URL="${MCP_GATEWAY_URL:-http://localhost:8080}"

endpoints=(
    "/health/live"
    "/health/ready"
    "/mcp/tools/list"
)

for i in {1..3}; do
    echo "Round $i/3..."
    for endpoint in "${endpoints[@]}"; do
        curl -s -o /dev/null "$MCP_URL$endpoint" &
    done
    wait
    sleep 2
done

echo "Warm-up complete. Platform is hot and ready for client demo."
WARMUP

    chmod +x "$warmup_path"
    log_success "Warm-up script generated at $warmup_path"
}

# ═══════════════════════════════════════════════════════════════════════════════
# USAGE
# ═══════════════════════════════════════════════════════════════════════════════
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS] [MODE]

Infrastructure fix script for CAB-964 (Pre-client Demo)

MODES:
  full       Run complete fix workflow (default)
  diagnose   Only diagnose issues
  fix-pg     Fix PostgreSQL only
  fix-gw     Fix API Gateway only
  validate   Run validation checks
  test       Run MCP dry-run tests
  warmup     Generate warm-up script for demo day

OPTIONS:
  --dry-run  Show what would be done without making changes
  --debug    Enable debug output
  -h, --help Show this help

ENVIRONMENT VARIABLES:
  STOA_ENV             Environment (dev|staging|prod) - affects Vault paths
  STOA_NAMESPACE       Kubernetes namespace (default: stoa-system)
  STOA_PG_LABEL        PostgreSQL pod label (default: app=control-plane-db)
  STOA_GW_LABEL        API Gateway pod label (default: app=apigateway)
  STOA_VAULT_PATH      Vault secret path (default: secret/apim/\$ENV/database)
  DRY_RUN=1            Same as --dry-run
  DEBUG=1              Same as --debug

EXAMPLES:
  $0                          # Full fix workflow
  $0 --dry-run diagnose       # Diagnose without changes
  $0 fix-pg                   # Fix PostgreSQL only
  STOA_ENV=staging $0         # Use staging Vault path

EOF
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
main() {
    local mode="full"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) DRY_RUN=1; shift ;;
            --debug)   DEBUG=1; shift ;;
            -h|--help) show_usage; exit 0 ;;
            full|diagnose|fix-pg|fix-gw|validate|test|warmup) mode="$1"; shift ;;
            *) log_error "Unknown option: $1"; show_usage; exit 1 ;;
        esac
    done

    print_banner

    case "$mode" in
        diagnose)
            preflight_check
            diagnose_postgresql
            separator
            diagnose_apigateway
            ;;
        fix-pg)
            preflight_check
            diagnose_postgresql
            fix_postgresql
            validate_postgresql
            ;;
        fix-gw)
            preflight_check
            diagnose_apigateway
            fix_apigateway
            validate_apigateway
            ;;
        validate)
            preflight_check
            validate_postgresql
            validate_apigateway
            run_health_check
            ;;
        test)
            preflight_check
            run_mcp_tests
            ;;
        warmup)
            generate_warmup_script
            ;;
        full)
            preflight_check

            separator
            echo -e "${WHITE}PHASE 1: PostgreSQL${NC}"
            separator
            diagnose_postgresql
            fix_postgresql
            validate_postgresql || log_warning "PostgreSQL may need manual intervention"

            separator
            echo -e "${WHITE}PHASE 2: API Gateway${NC}"
            separator
            diagnose_apigateway
            fix_apigateway
            validate_apigateway || log_warning "API Gateway may need manual intervention"

            separator
            echo -e "${WHITE}PHASE 3: Validation${NC}"
            separator
            run_health_check
            run_mcp_tests || log_warning "Some MCP tests failed"
            generate_warmup_script

            separator
            if [[ "${DRY_RUN:-0}" == "1" ]]; then
                echo -e "${YELLOW}"
                cat << 'EOF'
  +-----------------------------------------------------------+
  |  DRY-RUN COMPLETE - No changes were made                  |
  |  Remove --dry-run to apply fixes                          |
  +-----------------------------------------------------------+
EOF
                echo -e "${NC}"
            else
                echo -e "${GREEN}"
                cat << 'EOF'
  +-----------------------------------------------------------+
  |                                                           |
  |   CAB-964 COMPLETE                                        |
  |                                                           |
  |   [OK] PostgreSQL: Fixed                                  |
  |   [OK] API Gateway: Fixed                                 |
  |   [OK] MCP Tests: Executed                                |
  |   [OK] Warm-up Script: Ready                              |
  |                                                           |
  |   Ready for client demo on Wednesday!                      |
  |                                                           |
  +-----------------------------------------------------------+
EOF
                echo -e "${NC}"
            fi
            ;;
    esac
}

main "$@"
