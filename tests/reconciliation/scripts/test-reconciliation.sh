#!/bin/bash
# test-reconciliation.sh
# End-to-end test for webMethods GitOps reconciliation
#
# Usage:
#   ./test-reconciliation.sh [--env dev|staging|prod] [--scenario all|crash|drift|add|delete]
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - curl installed
#   - jq installed
#   - Access to webMethods Gateway API
#   - Access to AWX API

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

ENV="${ENV:-dev}"
SCENARIO="${SCENARIO:-all}"
NAMESPACE="${NAMESPACE:-stoa-system}"
GITOPS_REPO="${GITOPS_REPO:-/tmp/stoa-gitops}"

# webMethods Gateway
WM_GATEWAY_URL="${WM_GATEWAY_URL:-http://apim-gateway.${NAMESPACE}.svc:9072}"
WM_ADMIN_USER="${WM_ADMIN_USER:-Administrator}"
WM_ADMIN_PASSWORD="${WM_ADMIN_PASSWORD:?WM_ADMIN_PASSWORD is required}"

# AWX
AWX_HOST="${AWX_HOST:-https://awx.stoa.cab-i.com}"
AWX_TOKEN="${AWX_TOKEN:?AWX_TOKEN is required}"
AWX_JOB_TEMPLATE_ID="${AWX_JOB_TEMPLATE_ID:-42}"

# Test parameters
RECONCILE_TIMEOUT=300  # 5 minutes
CHECK_INTERVAL=10

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✅ OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠️ WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[❌ FAIL]${NC} $1"
}

log_section() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# API call to webMethods Gateway
wm_api() {
    local method=$1
    local endpoint=$2
    local data=${3:-}

    if [ -n "$data" ]; then
        curl -s -X "$method" \
            "${WM_GATEWAY_URL}/rest/apigateway${endpoint}" \
            -u "${WM_ADMIN_USER}:${WM_ADMIN_PASSWORD}" \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -d "$data"
    else
        curl -s -X "$method" \
            "${WM_GATEWAY_URL}/rest/apigateway${endpoint}" \
            -u "${WM_ADMIN_USER}:${WM_ADMIN_PASSWORD}" \
            -H "Accept: application/json"
    fi
}

# Get list of APIs from Gateway
get_gateway_apis() {
    wm_api GET "/apis" | jq -r '.apiResponse[].apiName // empty' | sort
}

# Get list of APIs from Git
get_git_apis() {
    find "${GITOPS_REPO}/webmethods/apis" -name "*.yaml" -exec basename {} .yaml \; | sort
}

# Trigger AWX reconciliation
trigger_reconciliation() {
    log_info "Triggering AWX reconciliation job..."

    local response=$(curl -s -w "\n%{http_code}" -X POST \
        "${AWX_HOST}/api/v2/job_templates/${AWX_JOB_TEMPLATE_ID}/launch/" \
        -H "Authorization: Bearer ${AWX_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"extra_vars\": {\"env\": \"${ENV}\", \"delete_orphans\": true}}")

    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    if [ "$http_code" -eq 201 ]; then
        local job_id=$(echo "$body" | jq -r '.id')
        echo "$job_id"
    else
        log_error "Failed to trigger AWX job (HTTP $http_code)"
        return 1
    fi
}

# Wait for AWX job completion
wait_for_job() {
    local job_id=$1
    local elapsed=0

    log_info "Waiting for AWX job $job_id to complete..."

    while [ $elapsed -lt $RECONCILE_TIMEOUT ]; do
        local status=$(curl -s \
            "${AWX_HOST}/api/v2/jobs/${job_id}/" \
            -H "Authorization: Bearer ${AWX_TOKEN}" \
            | jq -r '.status')

        case $status in
            successful)
                log_success "Job completed successfully in ${elapsed}s"
                return 0
                ;;
            failed|error|canceled)
                log_error "Job failed with status: $status"
                return 1
                ;;
            *)
                echo -n "."
                sleep $CHECK_INTERVAL
                elapsed=$((elapsed + CHECK_INTERVAL))
                ;;
        esac
    done

    log_error "Timeout waiting for job completion"
    return 1
}

# Compare Gateway state with Git
compare_state() {
    local gateway_apis=$(get_gateway_apis)
    local git_apis=$(get_git_apis)

    local missing_from_gateway=$(comm -23 <(echo "$git_apis") <(echo "$gateway_apis"))
    local orphans_on_gateway=$(comm -13 <(echo "$git_apis") <(echo "$gateway_apis"))
    local in_sync=$(comm -12 <(echo "$git_apis") <(echo "$gateway_apis"))

    echo "IN_SYNC: $in_sync"
    echo "MISSING: $missing_from_gateway"
    echo "ORPHANS: $orphans_on_gateway"
}

# =============================================================================
# Test Scenarios
# =============================================================================

# Scenario 1: Simulate Gateway crash/restart
test_crash_recovery() {
    log_section "SCENARIO 1: Gateway Crash Recovery"

    # Step 1: Record current state
    log_info "Step 1: Recording current Gateway state..."
    local before_apis=$(get_gateway_apis)
    local api_count=$(echo "$before_apis" | wc -l)
    log_info "Found $api_count APIs on Gateway"

    # Step 2: Delete all APIs (simulate crash)
    log_info "Step 2: Simulating crash by deleting all APIs..."
    for api in $before_apis; do
        local api_id=$(wm_api GET "/apis" | jq -r ".apiResponse[] | select(.apiName==\"$api\") | .id")
        if [ -n "$api_id" ]; then
            wm_api DELETE "/apis/$api_id" > /dev/null 2>&1 || true
            echo -n "."
        fi
    done
    echo ""

    # Verify deletion
    local after_delete=$(get_gateway_apis | wc -l)
    if [ "$after_delete" -eq 0 ]; then
        log_success "All APIs deleted (simulating crash)"
    else
        log_warning "$after_delete APIs still present"
    fi

    # Step 3: Trigger reconciliation
    log_info "Step 3: Triggering reconciliation..."
    local start_time=$(date +%s)
    local job_id=$(trigger_reconciliation)

    if [ -z "$job_id" ]; then
        log_error "Failed to trigger reconciliation"
        return 1
    fi

    # Step 4: Wait for completion
    log_info "Step 4: Waiting for reconciliation (Job ID: $job_id)..."
    if ! wait_for_job "$job_id"; then
        return 1
    fi

    local end_time=$(date +%s)
    local rto=$((end_time - start_time))

    # Step 5: Verify recovery
    log_info "Step 5: Verifying API recovery..."
    local after_apis=$(get_gateway_apis)
    local recovered_count=$(echo "$after_apis" | wc -l)

    if [ "$recovered_count" -eq "$api_count" ]; then
        log_success "All $api_count APIs recovered!"
        log_success "RTO (Recovery Time Objective): ${rto}s"
        return 0
    else
        log_error "Only $recovered_count/$api_count APIs recovered"
        return 1
    fi
}

# Scenario 2: Detect and fix drift
test_drift_detection() {
    log_section "SCENARIO 2: Drift Detection & Correction"

    # Step 1: Get a random API
    log_info "Step 1: Selecting an API to modify..."
    local api_name=$(get_gateway_apis | head -1)

    if [ -z "$api_name" ]; then
        log_warning "No APIs found, skipping drift test"
        return 0
    fi

    local api_id=$(wm_api GET "/apis" | jq -r ".apiResponse[] | select(.apiName==\"$api_name\") | .id")
    log_info "Selected API: $api_name (ID: $api_id)"

    # Step 2: Create drift by modifying API directly
    log_info "Step 2: Creating drift by modifying API description..."
    local drift_marker="DRIFT-TEST-$(date +%s)"
    wm_api PUT "/apis/$api_id" "{\"apiDescription\": \"$drift_marker\"}" > /dev/null
    log_success "API modified with drift marker"

    # Step 3: Trigger reconciliation
    log_info "Step 3: Triggering reconciliation..."
    local job_id=$(trigger_reconciliation)

    if ! wait_for_job "$job_id"; then
        return 1
    fi

    # Step 4: Verify drift was corrected
    log_info "Step 4: Verifying drift correction..."
    local current_desc=$(wm_api GET "/apis/$api_id" | jq -r '.apiResponse.apiDescription // ""')

    if [[ "$current_desc" != *"$drift_marker"* ]]; then
        log_success "Drift corrected! Description restored from Git"
        return 0
    else
        log_error "Drift NOT corrected. Description still contains drift marker"
        return 1
    fi
}

# Scenario 3: Add new API via Git
test_add_api() {
    log_section "SCENARIO 3: Add New API via Git"

    local test_api_name="test-api-$(date +%s)"
    local test_api_file="${GITOPS_REPO}/webmethods/apis/${test_api_name}.yaml"

    # Step 1: Create new API file
    log_info "Step 1: Creating new API file in Git..."
    cat > "$test_api_file" << EOF
apiVersion: stoa.io/v1
kind: WebMethodsAPI
metadata:
  name: ${test_api_name}
  version: "1.0.0"
  description: "Test API for reconciliation validation"
  tags:
    - test
    - automated
spec:
  type: REST
  basePath: /api/test/v1
  backend:
    alias: test-backend
  policies: []
  auth:
    type: none
  resources:
    - path: /health
      methods: [GET]
EOF
    log_success "Created $test_api_file"

    # Step 2: Trigger reconciliation
    log_info "Step 2: Triggering reconciliation..."
    local job_id=$(trigger_reconciliation)

    if ! wait_for_job "$job_id"; then
        rm -f "$test_api_file"
        return 1
    fi

    # Step 3: Verify API was created
    log_info "Step 3: Verifying API creation on Gateway..."
    local gateway_apis=$(get_gateway_apis)

    if echo "$gateway_apis" | grep -q "$test_api_name"; then
        log_success "API $test_api_name created on Gateway!"

        # Cleanup
        log_info "Cleaning up test API..."
        rm -f "$test_api_file"
        trigger_reconciliation > /dev/null

        return 0
    else
        log_error "API $test_api_name NOT found on Gateway"
        rm -f "$test_api_file"
        return 1
    fi
}

# Scenario 4: Delete API via Git
test_delete_api() {
    log_section "SCENARIO 4: Delete API via Git"

    # Step 1: Create a temporary API first
    local test_api_name="delete-test-api-$(date +%s)"
    local test_api_file="${GITOPS_REPO}/webmethods/apis/${test_api_name}.yaml"

    log_info "Step 1: Creating temporary API..."
    cat > "$test_api_file" << EOF
apiVersion: stoa.io/v1
kind: WebMethodsAPI
metadata:
  name: ${test_api_name}
  version: "1.0.0"
  description: "Temporary API for delete test"
spec:
  type: REST
  basePath: /api/delete-test/v1
  backend:
    alias: test-backend
  policies: []
EOF

    local job_id=$(trigger_reconciliation)
    wait_for_job "$job_id" || return 1

    # Verify creation
    if ! get_gateway_apis | grep -q "$test_api_name"; then
        log_error "Failed to create test API"
        rm -f "$test_api_file"
        return 1
    fi
    log_success "Test API created"

    # Step 2: Delete API file from Git
    log_info "Step 2: Deleting API file from Git..."
    rm -f "$test_api_file"

    # Step 3: Trigger reconciliation
    log_info "Step 3: Triggering reconciliation..."
    job_id=$(trigger_reconciliation)

    if ! wait_for_job "$job_id"; then
        return 1
    fi

    # Step 4: Verify API was deleted
    log_info "Step 4: Verifying API deletion from Gateway..."

    if ! get_gateway_apis | grep -q "$test_api_name"; then
        log_success "API $test_api_name deleted from Gateway!"
        return 0
    else
        log_error "API $test_api_name still exists on Gateway"
        return 1
    fi
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    log_section "webMethods GitOps Reconciliation Test Suite"

    echo "Configuration:"
    echo "  Environment: $ENV"
    echo "  Scenario: $SCENARIO"
    echo "  Gateway URL: $WM_GATEWAY_URL"
    echo "  AWX Host: $AWX_HOST"
    echo "  GitOps Repo: $GITOPS_REPO"
    echo ""

    # Verify prerequisites
    log_info "Checking prerequisites..."

    if ! command -v jq &> /dev/null; then
        log_error "jq is required but not installed"
        exit 1
    fi

    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi

    # Check Gateway connectivity
    if ! wm_api GET "/health" > /dev/null 2>&1; then
        log_error "Cannot connect to webMethods Gateway"
        exit 1
    fi
    log_success "Gateway connectivity OK"

    # Check AWX connectivity
    if ! curl -s -o /dev/null -w "%{http_code}" \
        "${AWX_HOST}/api/v2/ping/" \
        -H "Authorization: Bearer ${AWX_TOKEN}" | grep -q "200"; then
        log_error "Cannot connect to AWX"
        exit 1
    fi
    log_success "AWX connectivity OK"

    # Run tests
    local passed=0
    local failed=0
    local results=()

    case $SCENARIO in
        all)
            for test in crash drift add delete; do
                if "test_${test}_recovery" 2>/dev/null || \
                   "test_${test}_detection" 2>/dev/null || \
                   "test_${test}_api" 2>/dev/null; then
                    passed=$((passed + 1))
                    results+=("✅ $test")
                else
                    failed=$((failed + 1))
                    results+=("❌ $test")
                fi
            done
            ;;
        crash)
            test_crash_recovery && passed=$((passed + 1)) || failed=$((failed + 1))
            ;;
        drift)
            test_drift_detection && passed=$((passed + 1)) || failed=$((failed + 1))
            ;;
        add)
            test_add_api && passed=$((passed + 1)) || failed=$((failed + 1))
            ;;
        delete)
            test_delete_api && passed=$((passed + 1)) || failed=$((failed + 1))
            ;;
        *)
            log_error "Unknown scenario: $SCENARIO"
            exit 1
            ;;
    esac

    # Summary
    log_section "Test Results Summary"

    echo "Results:"
    for result in "${results[@]:-}"; do
        echo "  $result"
    done
    echo ""
    echo "Passed: $passed"
    echo "Failed: $failed"
    echo ""

    if [ $failed -eq 0 ]; then
        log_success "All tests passed! 🎉"
        exit 0
    else
        log_error "Some tests failed"
        exit 1
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            ENV="$2"
            shift 2
            ;;
        --scenario)
            SCENARIO="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--env dev|staging|prod] [--scenario all|crash|drift|add|delete]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

main
