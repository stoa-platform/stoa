#!/usr/bin/env bash
# STOA Gateway Load Benchmark
# Uses hey (https://github.com/rakyll/hey) to measure throughput and latency
# across multiple concurrency levels and feature configurations.
#
# Usage:
#   ./load-test.sh --target http://localhost:8080 --admin http://localhost:8080
#   ./load-test.sh --target http://51.83.45.13:8080 --admin http://51.83.45.13:8080 --duration 60
#
# Prerequisites: hey (brew install hey)

set -euo pipefail

# --- Defaults ---
TARGET_URL=""
ADMIN_URL=""
DURATION=30
CONCURRENCY_LEVELS=(1 10 50 100 500)
ADMIN_TOKEN="${STOA_ADMIN_TOKEN:-${STOA_ADMIN_API_TOKEN:-}}"
OUTPUT_DIR="./benchmark-results"
PROXY_PATH="/httpbin/get"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

usage() {
    cat <<EOF
STOA Gateway Load Benchmark

Usage: $0 --target <url> [--admin <url>] [--duration <sec>] [--output <dir>]

Options:
  --target   <url>   Gateway base URL (required). Example: http://localhost:8080
  --admin    <url>   Admin API base URL (defaults to --target)
  --duration <sec>   Duration per test in seconds (default: 30)
  --output   <dir>   Output directory for results (default: ./benchmark-results)
  --help             Show this help

Environment:
  STOA_ADMIN_TOKEN   Admin API token (from Infisical: prod/gateway/arena/ADMIN_API_TOKEN)

Examples:
  # Local Docker Compose
  $0 --target http://localhost:8080

  # VPS deployment
  $0 --target http://51.83.45.13:8080 --duration 60
EOF
    exit 0
}

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)  TARGET_URL="$2"; shift 2 ;;
        --admin)   ADMIN_URL="$2"; shift 2 ;;
        --duration) DURATION="$2"; shift 2 ;;
        --output)  OUTPUT_DIR="$2"; shift 2 ;;
        --help)    usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$TARGET_URL" ]]; then
    echo -e "${RED}Error: --target is required${NC}"
    usage
fi

ADMIN_URL="${ADMIN_URL:-$TARGET_URL}"

# --- Check prerequisites ---
if ! command -v hey &>/dev/null; then
    echo -e "${RED}Error: hey is not installed. Install with: brew install hey${NC}"
    exit 1
fi

# --- Machine profile ---
machine_profile() {
    echo "## Machine Profile"
    echo ""
    if [[ "$(uname)" == "Darwin" ]]; then
        local cpu_model
        cpu_model=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "unknown")
        local cpu_cores
        cpu_cores=$(sysctl -n hw.ncpu 2>/dev/null || echo "?")
        local ram_bytes
        ram_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
        local ram_gb=$(( ram_bytes / 1073741824 ))
        echo "| Field | Value |"
        echo "|-------|-------|"
        echo "| OS | macOS $(sw_vers -productVersion 2>/dev/null || echo '?') |"
        echo "| CPU | ${cpu_model} |"
        echo "| Cores | ${cpu_cores} |"
        echo "| RAM | ${ram_gb} GB |"
    else
        local cpu_model
        cpu_model=$(lscpu 2>/dev/null | grep "Model name" | sed 's/.*:\s*//' || echo "unknown")
        local cpu_cores
        cpu_cores=$(nproc 2>/dev/null || echo "?")
        local ram_kb
        ram_kb=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
        local ram_gb=$(( ram_kb / 1048576 ))
        echo "| Field | Value |"
        echo "|-------|-------|"
        echo "| OS | $(uname -sr) |"
        echo "| CPU | ${cpu_model} |"
        echo "| Cores | ${cpu_cores} |"
        echo "| RAM | ${ram_gb} GB |"
    fi
    echo "| Tool | hey $(hey 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9.]+' || echo '?') |"
    echo "| Date | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
    echo "| Target | ${TARGET_URL} |"
    echo "| Duration | ${DURATION}s per test |"
    echo ""
}

# --- Admin API helpers ---
admin_request() {
    local method="$1" path="$2"
    shift 2
    curl -sf -X "$method" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        "${ADMIN_URL}${path}" "$@"
}

setup_proxy_route() {
    echo -e "${CYAN}  Setting up proxy route...${NC}" >&2
    admin_request POST "/admin/apis" -d '{
        "api_id": "bench-httpbin",
        "name": "bench-httpbin",
        "upstream_url": "https://httpbin.org",
        "listen_path": "/httpbin",
        "strip_listen_path": true,
        "auth_required": false,
        "rate_limit_enabled": false
    }' >/dev/null 2>&1 || true
}

enable_auth() {
    echo -e "${CYAN}  Enabling API key auth...${NC}" >&2
    admin_request POST "/admin/apis" -d '{
        "api_id": "bench-httpbin",
        "name": "bench-httpbin",
        "upstream_url": "https://httpbin.org",
        "listen_path": "/httpbin",
        "strip_listen_path": true,
        "auth_required": true,
        "rate_limit_enabled": false
    }' >/dev/null 2>&1 || true
}

enable_auth_and_ratelimit() {
    echo -e "${CYAN}  Enabling auth + rate limit...${NC}" >&2
    admin_request POST "/admin/apis" -d '{
        "api_id": "bench-httpbin",
        "name": "bench-httpbin",
        "upstream_url": "https://httpbin.org",
        "listen_path": "/httpbin",
        "strip_listen_path": true,
        "auth_required": true,
        "rate_limit_enabled": true
    }' >/dev/null 2>&1 || true
    admin_request POST "/admin/policies" -d '{
        "policy_id": "bench-ratelimit",
        "api_id": "bench-httpbin",
        "policy_type": "rate_limit",
        "config": {
            "requests_per_minute": 100000
        }
    }' >/dev/null 2>&1 || true
}

cleanup_route() {
    echo -e "${CYAN}  Cleaning up...${NC}" >&2
    admin_request DELETE "/admin/apis/bench-httpbin" >/dev/null 2>&1 || true
    admin_request DELETE "/admin/policies/bench-ratelimit" >/dev/null 2>&1 || true
}

# --- Run hey and extract stats ---
run_hey() {
    local url="$1" concurrency="$2" extra_headers="${3:-}"
    local hey_args=(-z "${DURATION}s" -c "$concurrency" -t 10 -q 0)

    if [[ -n "$extra_headers" ]]; then
        hey_args+=(-H "$extra_headers")
    fi

    hey "${hey_args[@]}" "$url" 2>/dev/null
}

parse_hey_output() {
    local output="$1"
    local rps p50 p95 p99 errors total

    rps=$(echo "$output" | grep "Requests/sec:" | awk '{printf "%.1f", $2}')
    total=$(echo "$output" | grep "^\s*Total:" | head -1 | awk '{print $2}')

    # Latency percentiles from the distribution section
    p50=$(echo "$output" | grep "50% in" | awk '{printf "%.3f", $3}')
    p95=$(echo "$output" | grep "95% in" | awk '{printf "%.3f", $3}')
    p99=$(echo "$output" | grep "99% in" | awk '{printf "%.3f", $3}')

    # Error count
    local status_200
    status_200=$(echo "$output" | grep "\[200\]" | awk '{print $2}' || echo "0")
    local total_requests
    total_requests=$(echo "$output" | grep "^\s*Total:" | head -1 | awk '{printf "%.0f", $2 * '"$rps"'}' 2>/dev/null || echo "0")
    # Get actual total from summary
    total_requests=$(echo "$output" | grep "^  Total:" | tail -1 | awk '{print $2}' || echo "0")

    # Count non-200 responses
    local error_lines
    error_lines=$(echo "$output" | grep "^\s*\[" | grep -v "\[200\]" || true)
    local error_count=0
    if [[ -n "$error_lines" ]]; then
        error_count=$(echo "$error_lines" | awk '{sum+=$2} END {print sum+0}')
    fi

    # Calculate error percentage from status code distribution
    local total_counted
    total_counted=$(echo "$output" | grep "^\s*\[" | awk '{sum+=$2} END {print sum+0}')
    local error_pct="0.0"
    if [[ "$total_counted" -gt 0 ]]; then
        error_pct=$(awk "BEGIN {printf \"%.1f\", ($error_count / $total_counted) * 100}")
    fi

    echo "${rps}|${p50}|${p95}|${p99}|${error_pct}"
}

# --- Format latency for display ---
fmt_latency() {
    local val="$1"
    if [[ -z "$val" || "$val" == "0.000" ]]; then
        echo "N/A"
        return
    fi
    local ms
    ms=$(awk "BEGIN {printf \"%.2f\", $val * 1000}")
    if (( $(awk "BEGIN {print ($ms < 1) ? 1 : 0}") )); then
        local us
        us=$(awk "BEGIN {printf \"%.0f\", $val * 1000000}")
        echo "${us}us"
    else
        echo "${ms}ms"
    fi
}

# --- Run a scenario ---
run_scenario() {
    local name="$1" url="$2" extra_headers="${3:-}"

    echo ""
    echo "### ${name}"
    echo ""
    echo "| Concurrency | RPS | P50 | P95 | P99 | Errors |"
    echo "|-------------|-----|-----|-----|-----|--------|"

    for c in "${CONCURRENCY_LEVELS[@]}"; do
        echo -e "${YELLOW}  Running ${name} @ c=${c}...${NC}" >&2
        local output
        output=$(run_hey "$url" "$c" "$extra_headers")
        local parsed
        parsed=$(parse_hey_output "$output")

        IFS='|' read -r rps p50 p95 p99 errors <<< "$parsed"
        echo "| ${c} | ${rps} | $(fmt_latency "$p50") | $(fmt_latency "$p95") | $(fmt_latency "$p99") | ${errors}% |"
    done
    echo ""
}

# --- Main ---
main() {
    mkdir -p "$OUTPUT_DIR"
    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local report="${OUTPUT_DIR}/benchmark-${timestamp}.md"

    echo -e "${GREEN}STOA Gateway Load Benchmark${NC}" >&2
    echo -e "${GREEN}Target: ${TARGET_URL}${NC}" >&2
    echo -e "${GREEN}Duration: ${DURATION}s per test${NC}" >&2
    echo -e "${GREEN}Concurrency levels: ${CONCURRENCY_LEVELS[*]}${NC}" >&2
    echo "" >&2

    {
        echo "# STOA Gateway Load Benchmark"
        echo ""
        echo "_Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)_"
        echo ""

        machine_profile

        # Scenario 1: Health check (baseline, no proxy)
        echo -e "${GREEN}[1/4] Health Check (baseline)${NC}" >&2
        run_scenario "Scenario 1: Health Check (baseline)" "${TARGET_URL}/health"

        # Scenario 2: Proxy passthrough (no auth, no rate limit)
        echo -e "${GREEN}[2/4] Proxy Passthrough${NC}" >&2
        setup_proxy_route
        sleep 1
        run_scenario "Scenario 2: Proxy Passthrough (no auth)" "${TARGET_URL}${PROXY_PATH}"

        # Scenario 3: Proxy + API key auth
        echo -e "${GREEN}[3/4] Proxy + Auth${NC}" >&2
        enable_auth
        sleep 1
        run_scenario "Scenario 3: Proxy + API Key Auth" \
            "${TARGET_URL}${PROXY_PATH}" \
            "X-API-Key: bench-test-key-2026"

        # Scenario 4: Proxy + Auth + Rate Limit
        echo -e "${GREEN}[4/4] Proxy + Auth + Rate Limit${NC}" >&2
        enable_auth_and_ratelimit
        sleep 1
        run_scenario "Scenario 4: Proxy + Auth + Rate Limit" \
            "${TARGET_URL}${PROXY_PATH}" \
            "X-API-Key: bench-test-key-2026"

        # Cleanup
        cleanup_route

        # Summary
        echo "## Notes"
        echo ""
        echo "- Each test runs for ${DURATION}s at the specified concurrency level"
        echo "- Gateway features are toggled via Admin API between scenarios"
        echo "- Latency includes upstream response time (httpbin.org or local backend)"
        echo "- Run 3x and take median for publishable results"
        echo "- Results vary by network, backend, and machine load"

    } > "$report"

    echo "" >&2
    echo -e "${GREEN}Report saved to: ${report}${NC}" >&2
    echo -e "${CYAN}Preview:${NC}" >&2
    cat "$report"
}

main
