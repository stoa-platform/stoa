#!/bin/bash
# =============================================================================
# OWASP ZAP Security Scanner
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# Runs OWASP ZAP security scans against STOA Platform
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ZAP_DIR="$PROJECT_ROOT/tests/security/zap"
RESULTS_DIR="$PROJECT_ROOT/tests/security/results"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
SCAN_TYPE="baseline"
ENVIRONMENT="dev"
TARGET_URL=""
AUTH_URL=""
DOCKER_MODE=false
ZAP_USER="${ZAP_USER:-}"
ZAP_PASSWORD="${ZAP_PASSWORD:-}"
FAIL_ON_WARN=false

# =============================================================================
# Functions
# =============================================================================

print_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║         STOA Platform - Security Scanner (OWASP ZAP)          ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Options:
    -t, --type TYPE       Scan type: baseline, full, api (default: baseline)
    -e, --env ENV         Environment: dev, staging, prod (default: dev)
    -u, --url URL         Custom target URL (overrides environment)
    --auth-url URL        Custom auth URL (Keycloak)
    --docker              Run ZAP in Docker container
    --fail-on-warn        Exit with error on warnings (not just failures)
    -h, --help            Show this help message

Scan Types:
    baseline    Passive scan only, safe for production (5 min)
    full        Active scan, attacks the application (30-60 min)
    api         API-focused scan using OpenAPI spec (15 min)

Examples:
    # Baseline scan against dev
    $(basename "$0") -t baseline -e dev

    # Full scan against staging
    $(basename "$0") -t full -e staging --docker

    # API scan with custom URL
    $(basename "$0") -t api -u https://api.example.com --docker

Environment Variables:
    ZAP_USER        Username for authenticated scans
    ZAP_PASSWORD    Password for authenticated scans

EOF
    exit 0
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get environment URLs
get_env_urls() {
    case "$ENVIRONMENT" in
        dev)
            TARGET_URL="${TARGET_URL:-https://api.dev.stoa.cab-i.com}"
            AUTH_URL="${AUTH_URL:-https://auth.dev.stoa.cab-i.com}"
            ;;
        staging)
            TARGET_URL="${TARGET_URL:-https://api.staging.stoa.cab-i.com}"
            AUTH_URL="${AUTH_URL:-https://auth.staging.stoa.cab-i.com}"
            ;;
        prod)
            TARGET_URL="${TARGET_URL:-https://api.stoa.cab-i.com}"
            AUTH_URL="${AUTH_URL:-https://auth.stoa.cab-i.com}"
            ;;
        *)
            log_error "Unknown environment: $ENVIRONMENT"
            exit 1
            ;;
    esac
}

# Check prerequisites
check_prereqs() {
    if $DOCKER_MODE; then
        if ! command -v docker &> /dev/null; then
            log_error "Docker is required but not installed"
            exit 1
        fi
    else
        if ! command -v zap.sh &> /dev/null && ! command -v zap-baseline.py &> /dev/null; then
            log_warn "ZAP not found locally. Switching to Docker mode."
            DOCKER_MODE=true
        fi
    fi

    # Create results directory
    mkdir -p "$RESULTS_DIR"
}

# Production safety check
check_production_safety() {
    if [[ "$ENVIRONMENT" == "prod" && "$SCAN_TYPE" != "baseline" ]]; then
        log_error "SAFETY: Only baseline scans are allowed in production!"
        log_error "Full and API scans perform active attacks and may disrupt the service."
        exit 1
    fi
}

# Run baseline scan
run_baseline_scan() {
    log_info "Starting baseline (passive) scan..."

    local report_name="baseline-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"

    if $DOCKER_MODE; then
        docker run --rm \
            -v "$ZAP_DIR:/zap/wrk:rw" \
            -v "$RESULTS_DIR:/zap/reports:rw" \
            -t ghcr.io/zaproxy/zaproxy:stable \
            zap-baseline.py \
            -t "$TARGET_URL" \
            -c "$ZAP_DIR/api-scan-rules.conf" \
            -r "${report_name}.html" \
            -J "${report_name}.json" \
            -I \
            --auto
    else
        zap-baseline.py \
            -t "$TARGET_URL" \
            -c "$ZAP_DIR/api-scan-rules.conf" \
            -r "$RESULTS_DIR/${report_name}.html" \
            -J "$RESULTS_DIR/${report_name}.json" \
            -I
    fi

    return $?
}

# Run full scan
run_full_scan() {
    log_info "Starting full (active) scan..."
    log_warn "This scan will attack the application. Only use in dev/staging!"

    local report_name="full-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"

    if $DOCKER_MODE; then
        docker run --rm \
            -v "$ZAP_DIR:/zap/wrk:rw" \
            -v "$RESULTS_DIR:/zap/reports:rw" \
            -e TARGET_URL="$TARGET_URL" \
            -e AUTH_URL="$AUTH_URL" \
            -e ZAP_USER="$ZAP_USER" \
            -e ZAP_PASSWORD="$ZAP_PASSWORD" \
            -t ghcr.io/zaproxy/zaproxy:stable \
            zap-full-scan.py \
            -t "$TARGET_URL" \
            -c "$ZAP_DIR/api-scan-rules.conf" \
            -r "${report_name}.html" \
            -J "${report_name}.json" \
            -m 60 \
            --auto
    else
        zap-full-scan.py \
            -t "$TARGET_URL" \
            -c "$ZAP_DIR/api-scan-rules.conf" \
            -r "$RESULTS_DIR/${report_name}.html" \
            -J "$RESULTS_DIR/${report_name}.json" \
            -m 60
    fi

    return $?
}

# Run API scan
run_api_scan() {
    log_info "Starting API scan..."

    local report_name="api-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"
    local openapi_url="${TARGET_URL}/openapi.json"

    if $DOCKER_MODE; then
        docker run --rm \
            -v "$ZAP_DIR:/zap/wrk:rw" \
            -v "$RESULTS_DIR:/zap/reports:rw" \
            -t ghcr.io/zaproxy/zaproxy:stable \
            zap-api-scan.py \
            -t "$openapi_url" \
            -f openapi \
            -c "$ZAP_DIR/api-scan-rules.conf" \
            -r "${report_name}.html" \
            -J "${report_name}.json" \
            --auto
    else
        zap-api-scan.py \
            -t "$openapi_url" \
            -f openapi \
            -c "$ZAP_DIR/api-scan-rules.conf" \
            -r "$RESULTS_DIR/${report_name}.html" \
            -J "$RESULTS_DIR/${report_name}.json"
    fi

    return $?
}

# Parse results
parse_results() {
    local json_file
    json_file=$(ls -t "$RESULTS_DIR"/*.json 2>/dev/null | head -1)

    if [[ -z "$json_file" ]]; then
        log_warn "No JSON report found"
        return 0
    fi

    log_info "Parsing results from: $json_file"

    # Count alerts by risk level
    local high_count=0
    local medium_count=0
    local low_count=0
    local info_count=0

    if command -v jq &> /dev/null; then
        high_count=$(jq '[.site[].alerts[] | select(.riskcode == "3")] | length' "$json_file" 2>/dev/null || echo 0)
        medium_count=$(jq '[.site[].alerts[] | select(.riskcode == "2")] | length' "$json_file" 2>/dev/null || echo 0)
        low_count=$(jq '[.site[].alerts[] | select(.riskcode == "1")] | length' "$json_file" 2>/dev/null || echo 0)
        info_count=$(jq '[.site[].alerts[] | select(.riskcode == "0")] | length' "$json_file" 2>/dev/null || echo 0)
    fi

    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "                    Security Scan Summary"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo -e "  ${RED}High Risk:${NC}     $high_count"
    echo -e "  ${YELLOW}Medium Risk:${NC}   $medium_count"
    echo -e "  ${BLUE}Low Risk:${NC}      $low_count"
    echo -e "  Info:          $info_count"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"

    # Determine exit code
    if [[ "$high_count" -gt 0 ]]; then
        log_error "High risk vulnerabilities found!"
        return 1
    elif [[ "$medium_count" -gt 0 && "$FAIL_ON_WARN" == "true" ]]; then
        log_warn "Medium risk vulnerabilities found (--fail-on-warn enabled)"
        return 1
    elif [[ "$medium_count" -gt 0 ]]; then
        log_warn "Medium risk vulnerabilities found"
        return 0
    else
        log_success "No significant vulnerabilities found"
        return 0
    fi
}

# Send Slack notification
send_slack_notification() {
    local status=$1
    local webhook_url="${SLACK_WEBHOOK_URL:-}"

    if [[ -z "$webhook_url" ]]; then
        return 0
    fi

    local color="good"
    local title="Security Scan Passed"

    if [[ "$status" != "0" ]]; then
        color="danger"
        title="Security Scan Failed"
    fi

    curl -s -X POST "$webhook_url" \
        -H "Content-Type: application/json" \
        -d "{
            \"attachments\": [{
                \"color\": \"$color\",
                \"title\": \"$title\",
                \"text\": \"Environment: $ENVIRONMENT\nScan Type: $SCAN_TYPE\nTarget: $TARGET_URL\",
                \"footer\": \"STOA Security Scanner\",
                \"ts\": $(date +%s)
            }]
        }" || true
}

# =============================================================================
# Main
# =============================================================================

main() {
    print_banner

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--type)
                SCAN_TYPE="$2"
                shift 2
                ;;
            -e|--env)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -u|--url)
                TARGET_URL="$2"
                shift 2
                ;;
            --auth-url)
                AUTH_URL="$2"
                shift 2
                ;;
            --docker)
                DOCKER_MODE=true
                shift
                ;;
            --fail-on-warn)
                FAIL_ON_WARN=true
                shift
                ;;
            -h|--help)
                usage
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                ;;
        esac
    done

    # Setup
    get_env_urls
    check_prereqs
    check_production_safety

    log_info "Configuration:"
    log_info "  Scan Type:   $SCAN_TYPE"
    log_info "  Environment: $ENVIRONMENT"
    log_info "  Target URL:  $TARGET_URL"
    log_info "  Docker Mode: $DOCKER_MODE"
    echo ""

    # Run appropriate scan
    local scan_exit_code=0
    case "$SCAN_TYPE" in
        baseline)
            run_baseline_scan || scan_exit_code=$?
            ;;
        full)
            run_full_scan || scan_exit_code=$?
            ;;
        api)
            run_api_scan || scan_exit_code=$?
            ;;
        *)
            log_error "Unknown scan type: $SCAN_TYPE"
            exit 1
            ;;
    esac

    # Parse and display results
    parse_results || scan_exit_code=$?

    # Send notification
    send_slack_notification "$scan_exit_code"

    # Show report location
    echo ""
    log_info "Reports saved to: $RESULTS_DIR"
    ls -la "$RESULTS_DIR" 2>/dev/null | tail -5

    exit $scan_exit_code
}

main "$@"
