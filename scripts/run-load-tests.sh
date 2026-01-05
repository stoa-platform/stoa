#!/bin/bash
# =============================================================================
# STOA Platform Load Testing Runner
# =============================================================================
# Phase 9.5 - Production Readiness
# Executes K6 load tests with configurable scenarios and environments
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOAD_TEST_DIR="${PROJECT_ROOT}/tests/load"
K6_DIR="${LOAD_TEST_DIR}/k6"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Defaults
SCENARIO="smoke"
ENVIRONMENT="dev"
OUTPUT_DIR="${LOAD_TEST_DIR}/results"
USE_DOCKER=false
START_STACK=false
VUS=""
DURATION=""

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Run K6 load tests against STOA Platform.

Options:
    -s, --scenario NAME    Test scenario: smoke, load, stress, spike (default: smoke)
    -e, --env ENV          Environment: dev, staging, prod (default: dev)
    -o, --output DIR       Output directory for results (default: tests/load/results)
    -d, --docker           Run K6 in Docker container
    --start-stack          Start InfluxDB + Grafana stack before tests
    --vus N                Override virtual users count
    --duration T           Override test duration (e.g., "5m", "1h")
    -h, --help             Show this help message

Examples:
    # Run smoke test against dev
    ./run-load-tests.sh -s smoke -e dev

    # Run load test with Docker and monitoring stack
    ./run-load-tests.sh -s load -e staging --docker --start-stack

    # Run stress test (not for production!)
    ./run-load-tests.sh -s stress -e dev

    # Custom VUs and duration
    ./run-load-tests.sh -s load --vus 50 --duration 2m

Environment Variables:
    TEST_USER              Keycloak username for authenticated tests
    TEST_PASSWORD          Keycloak password
    CLIENT_SECRET          Keycloak client secret (for service account)
    SLACK_WEBHOOK_URL      Slack webhook for notifications

Notes:
    - Stress and spike tests are BLOCKED for production environment
    - For production, only smoke tests are allowed
    - Results are saved to: ${OUTPUT_DIR}/<scenario>-<timestamp>
EOF
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    if [[ "$USE_DOCKER" == "true" ]]; then
        if ! command -v docker &> /dev/null; then
            log_error "Docker is required but not installed"
            exit 1
        fi
        if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
            log_error "Docker Compose is required but not installed"
            exit 1
        fi
    else
        if ! command -v k6 &> /dev/null; then
            log_error "K6 is required but not installed"
            log_info "Install with: brew install k6 (macOS) or see https://k6.io/docs/getting-started/installation/"
            exit 1
        fi
    fi
}

validate_scenario() {
    case "$SCENARIO" in
        smoke|load|stress|spike)
            return 0
            ;;
        *)
            log_error "Invalid scenario: $SCENARIO"
            log_info "Valid scenarios: smoke, load, stress, spike"
            exit 1
            ;;
    esac
}

validate_environment() {
    case "$ENVIRONMENT" in
        dev|staging|prod|production)
            # Block dangerous tests in production
            if [[ "$ENVIRONMENT" == "prod" || "$ENVIRONMENT" == "production" ]]; then
                if [[ "$SCENARIO" == "stress" || "$SCENARIO" == "spike" ]]; then
                    log_error "BLOCKED: Cannot run $SCENARIO tests against production!"
                    log_info "Use smoke test for production: $0 -s smoke -e prod"
                    exit 1
                fi
            fi
            return 0
            ;;
        *)
            log_error "Invalid environment: $ENVIRONMENT"
            log_info "Valid environments: dev, staging, prod"
            exit 1
            ;;
    esac
}

start_monitoring_stack() {
    log_info "Starting monitoring stack (InfluxDB + Grafana)..."
    cd "$LOAD_TEST_DIR"

    docker compose up -d influxdb grafana

    log_info "Waiting for services to be ready..."
    sleep 10

    log_success "Monitoring stack started"
    log_info "Grafana available at: http://localhost:3001 (admin/admin)"
}

run_k6_local() {
    local script_path="${K6_DIR}/scenarios/${SCENARIO}.js"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local result_dir="${OUTPUT_DIR}/${SCENARIO}-${timestamp}"

    mkdir -p "$result_dir"

    log_info "Running K6 test: $SCENARIO"
    log_info "Environment: $ENVIRONMENT"
    log_info "Results: $result_dir"

    local k6_args=(
        "run"
        "--out" "json=${result_dir}/results.json"
        "-e" "ENVIRONMENT=${ENVIRONMENT}"
    )

    # Add optional overrides
    if [[ -n "$VUS" ]]; then
        k6_args+=("--vus" "$VUS")
    fi
    if [[ -n "$DURATION" ]]; then
        k6_args+=("--duration" "$DURATION")
    fi

    # Add InfluxDB output if stack is running
    if docker ps | grep -q stoa-influxdb 2>/dev/null; then
        k6_args+=("--out" "influxdb=http://localhost:8086/k6")
    fi

    k6_args+=("$script_path")

    # Export auth credentials if available
    export TEST_USER="${TEST_USER:-}"
    export TEST_PASSWORD="${TEST_PASSWORD:-}"
    export CLIENT_SECRET="${CLIENT_SECRET:-}"

    # Run K6
    if k6 "${k6_args[@]}" 2>&1 | tee "${result_dir}/output.log"; then
        log_success "Test completed successfully"
    else
        log_warn "Test completed with threshold failures"
    fi

    # Generate summary
    log_info "Results saved to: $result_dir"
}

run_k6_docker() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local result_dir="${OUTPUT_DIR}/${SCENARIO}-${timestamp}"

    mkdir -p "$result_dir"

    log_info "Running K6 in Docker: $SCENARIO"
    log_info "Environment: $ENVIRONMENT"

    cd "$LOAD_TEST_DIR"

    local docker_cmd="docker compose run --rm"
    docker_cmd+=" -e ENVIRONMENT=${ENVIRONMENT}"
    docker_cmd+=" -e TEST_USER=${TEST_USER:-}"
    docker_cmd+=" -e TEST_PASSWORD=${TEST_PASSWORD:-}"
    docker_cmd+=" -e CLIENT_SECRET=${CLIENT_SECRET:-}"

    local k6_cmd="run --out json=/scripts/results/results.json"

    if [[ -n "$VUS" ]]; then
        k6_cmd+=" --vus $VUS"
    fi
    if [[ -n "$DURATION" ]]; then
        k6_cmd+=" --duration $DURATION"
    fi

    k6_cmd+=" /scripts/scenarios/${SCENARIO}.js"

    # Create results directory in k6 folder for Docker mount
    mkdir -p "${K6_DIR}/results"

    if $docker_cmd k6 $k6_cmd 2>&1 | tee "${result_dir}/output.log"; then
        log_success "Test completed successfully"
    else
        log_warn "Test completed with threshold failures"
    fi

    # Move results
    if [[ -f "${K6_DIR}/results/results.json" ]]; then
        mv "${K6_DIR}/results/results.json" "${result_dir}/"
    fi

    log_info "Results saved to: $result_dir"
}

send_slack_notification() {
    local status=$1
    local message=$2

    if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
        return 0
    fi

    local color="good"
    if [[ "$status" == "failed" ]]; then
        color="danger"
    elif [[ "$status" == "warning" ]]; then
        color="warning"
    fi

    curl -s -X POST -H 'Content-type: application/json' \
        --data "{\"attachments\":[{\"color\":\"${color}\",\"title\":\"K6 Load Test: ${SCENARIO}\",\"text\":\"${message}\",\"fields\":[{\"title\":\"Environment\",\"value\":\"${ENVIRONMENT}\",\"short\":true},{\"title\":\"Scenario\",\"value\":\"${SCENARIO}\",\"short\":true}]}]}" \
        "$SLACK_WEBHOOK_URL" > /dev/null
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--scenario)
                SCENARIO="$2"
                shift 2
                ;;
            -e|--env)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -o|--output)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            -d|--docker)
                USE_DOCKER=true
                shift
                ;;
            --start-stack)
                START_STACK=true
                shift
                ;;
            --vus)
                VUS="$2"
                shift 2
                ;;
            --duration)
                DURATION="$2"
                shift 2
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    echo ""
    echo "=============================================="
    echo "  STOA Platform Load Testing"
    echo "=============================================="
    echo ""

    # Validation
    validate_scenario
    validate_environment
    check_prerequisites

    # Create output directory
    mkdir -p "$OUTPUT_DIR"

    # Start monitoring stack if requested
    if [[ "$START_STACK" == "true" ]]; then
        start_monitoring_stack
    fi

    # Run tests
    if [[ "$USE_DOCKER" == "true" ]]; then
        run_k6_docker
    else
        run_k6_local
    fi

    echo ""
    echo "=============================================="
    echo "  Test Complete"
    echo "=============================================="
    echo ""

    # Send notification
    send_slack_notification "success" "Load test completed for ${SCENARIO} on ${ENVIRONMENT}"
}

main "$@"
