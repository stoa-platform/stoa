#!/usr/bin/env bash
# STOA Control Plane API Benchmark Runner
#
# Wrapper around locust that handles profile selection, auth token
# acquisition, result collection, and markdown report generation.
#
# Usage:
#   ./run-api-bench.sh                          # smoke profile, localhost
#   ./run-api-bench.sh --profile load --host https://api.gostoa.dev
#   ./run-api-bench.sh --profile stress --tags health
#
# Prerequisites: pip install locust
# Auth: set BENCH_AUTH_TOKEN or KEYCLOAK_* vars for auto-acquisition

set -euo pipefail

# --- Defaults ---
PROFILE="smoke"
HOST="http://localhost:8000"
TAGS=""
OUTPUT_DIR="./benchmark-results"
EXTRA_ARGS=""

# --- Colors ---
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$(cd "${SCRIPT_DIR}/../../control-plane-api/benchmarks" && pwd)"

usage() {
    cat <<EOF
STOA Control Plane API Benchmark

Usage: $0 [OPTIONS]

Options:
  --profile <name>    Profile: smoke (default), load, stress, soak
  --host <url>        API base URL (default: http://localhost:8000)
  --tags <tags>       Locust tags to include (e.g., "health", "portal")
  --output <dir>      Output directory (default: ./benchmark-results)
  --help              Show this help

Profiles:
  smoke    5 users,  30s   — quick sanity check
  load     50 users, 120s  — standard load test
  stress   200 users, 180s — find breaking points
  soak     30 users, 600s  — stability over time

Environment:
  BENCH_AUTH_TOKEN    Bearer token for authenticated endpoints
  BENCH_TENANT_ID    Tenant ID for scoped requests (default: oasis)
  BENCH_API_URL      Override --host

Examples:
  # Quick health check benchmark
  $0 --profile smoke --tags health

  # Full load test against staging
  $0 --profile load --host https://api-staging.gostoa.dev

  # Stress test portal endpoints only
  $0 --profile stress --tags portal
EOF
    exit 0
}

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) PROFILE="$2"; shift 2 ;;
        --host)    HOST="$2"; shift 2 ;;
        --tags)    TAGS="$2"; shift 2 ;;
        --output)  OUTPUT_DIR="$2"; shift 2 ;;
        --help)    usage ;;
        *)         EXTRA_ARGS="${EXTRA_ARGS} $1"; shift ;;
    esac
done

# --- Resolve profile ---
case "$PROFILE" in
    smoke)  USERS=5;   SPAWN=5;  RUNTIME="30s"  ;;
    load)   USERS=50;  SPAWN=10; RUNTIME="120s" ;;
    stress) USERS=200; SPAWN=20; RUNTIME="180s" ;;
    soak)   USERS=30;  SPAWN=5;  RUNTIME="600s" ;;
    *)
        echo -e "${RED}Error: Unknown profile '${PROFILE}'. Use: smoke, load, stress, soak${NC}"
        exit 1
        ;;
esac

# --- Check locust ---
if ! command -v locust &>/dev/null; then
    echo -e "${RED}Error: locust is not installed. Install with: pip install locust${NC}"
    exit 1
fi

# --- Auto-acquire token if not set ---
if [[ -z "${BENCH_AUTH_TOKEN:-}" ]] && [[ -n "${KEYCLOAK_URL:-}" ]]; then
    echo -e "${CYAN}Acquiring auth token from Keycloak...${NC}"
    BENCH_AUTH_TOKEN=$(curl -sf -X POST \
        "${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM:-stoa}/protocol/openid-connect/token" \
        -d "grant_type=client_credentials" \
        -d "client_id=${KEYCLOAK_CLIENT_ID:-stoa-bench}" \
        -d "client_secret=${KEYCLOAK_CLIENT_SECRET}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null) || {
        echo -e "${YELLOW}Warning: Could not acquire token. Running without auth.${NC}"
        BENCH_AUTH_TOKEN=""
    }
    export BENCH_AUTH_TOKEN
fi

# --- Setup output ---
mkdir -p "${OUTPUT_DIR}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CSV_PREFIX="${OUTPUT_DIR}/bench-${PROFILE}-${TIMESTAMP}"

echo -e "${GREEN}=== STOA Control Plane API Benchmark ===${NC}"
echo -e "  Profile:  ${CYAN}${PROFILE}${NC} (${USERS} users, spawn ${SPAWN}/s, ${RUNTIME})"
echo -e "  Host:     ${CYAN}${HOST}${NC}"
echo -e "  Tags:     ${CYAN}${TAGS:-all}${NC}"
echo -e "  Output:   ${CYAN}${CSV_PREFIX}*${NC}"
echo ""

# --- Build locust command ---
LOCUST_CMD=(
    locust
    -f "${BENCH_DIR}/locustfile.py"
    --headless
    --host "${HOST}"
    -u "${USERS}"
    -r "${SPAWN}"
    --run-time "${RUNTIME}"
    --csv "${CSV_PREFIX}"
    --csv-full-history
    --print-stats
    --only-summary
)

if [[ -n "${TAGS}" ]]; then
    LOCUST_CMD+=(--tags "${TAGS}")
fi

# shellcheck disable=SC2086
"${LOCUST_CMD[@]}" ${EXTRA_ARGS} || true

echo ""
echo -e "${GREEN}=== Generating Report ===${NC}"

# --- Generate markdown report ---
REPORT="${OUTPUT_DIR}/report-${PROFILE}-${TIMESTAMP}.md"
cd "${SCRIPT_DIR}/../../control-plane-api" && \
    python3 -m benchmarks.report "${CSV_PREFIX}" > "${REPORT}" 2>/dev/null || {
    echo -e "${YELLOW}Warning: Could not generate markdown report (missing CSV data?)${NC}"
}

if [[ -f "${REPORT}" ]]; then
    echo -e "${GREEN}Report: ${REPORT}${NC}"
    echo ""
    cat "${REPORT}"
fi

echo ""
echo -e "${GREEN}CSV files: ${CSV_PREFIX}_*.csv${NC}"
echo -e "${GREEN}Done.${NC}"
