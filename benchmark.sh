#!/usr/bin/env bash
# STOA Platform - OSS Killer DX Benchmark
# Usage: ./benchmark.sh [--ci]
#
# Targets (OSS Killer Standard):
#   Cold start: < 120s
#   Warm start: < 30s
#   First API:  < 0.5s

set -euo pipefail

# Configuration
TARGET_COLD=120
TARGET_WARM=30
TARGET_API=0.5
SERVICES="postgres redis keycloak control-plane"

# Colors (disabled in CI)
if [[ "${CI:-}" == "true" ]] || [[ "${1:-}" == "--ci" ]]; then
    GREEN="" RED="" RESET="" BOLD=""
else
    GREEN="\033[0;32m" RED="\033[0;31m" RESET="\033[0m" BOLD="\033[1m"
fi

# Cross-platform helpers
get_cpu() {
    if [[ "$(uname)" == "Darwin" ]]; then
        sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Unknown"
    else
        grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "Unknown"
    fi
}

get_ram() {
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "$(($(sysctl -n hw.memsize) / 1024 / 1024 / 1024)) GB"
    else
        free -h 2>/dev/null | awk '/Mem:/{print $2}' || echo "Unknown"
    fi
}

get_time() {
    python3 -c 'import time; print(time.time())'
}

calc_duration() {
    python3 -c "print(f'{$2 - $1:.2f}')"
}

check_target() {
    local value=$1 target=$2
    python3 -c "exit(0 if $value < $target else 1)"
}

status_icon() {
    if check_target "$1" "$2"; then
        echo -e "${GREEN}PASS${RESET}"
    else
        echo -e "${RED}FAIL${RESET}"
    fi
}

# Header
echo -e "${BOLD}STOA Platform - OSS Killer DX Benchmark${RESET}"
echo "========================================"
echo ""

# Machine profile
echo "## Machine Profile"
echo ""
echo "| Property | Value |"
echo "|----------|-------|"
echo "| Date | $(date -Iseconds) |"
echo "| OS | $(uname -s) $(uname -r) |"
echo "| CPU | $(get_cpu) |"
echo "| RAM | $(get_ram) |"
echo "| Docker | $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'N/A') |"
echo ""

# Clean slate
echo "Preparing environment..."
docker compose down -v > /dev/null 2>&1 || true

# Results storage
declare -A RESULTS
declare -A STATUS
FAILED=0

# Cold start benchmark
echo -n "Running cold start benchmark... "
START=$(get_time)
docker compose up -d --build $SERVICES > /dev/null 2>&1
until curl -sf http://localhost:8080/health > /dev/null 2>&1; do sleep 0.5; done
END=$(get_time)
RESULTS[cold]=$(calc_duration "$START" "$END")
if check_target "${RESULTS[cold]}" "$TARGET_COLD"; then
    STATUS[cold]="PASS"
    echo -e "${GREEN}${RESULTS[cold]}s${RESET}"
else
    STATUS[cold]="FAIL"
    FAILED=1
    echo -e "${RED}${RESULTS[cold]}s (FAILED)${RESET}"
fi

# Warm start benchmark
echo -n "Running warm start benchmark... "
docker compose down > /dev/null 2>&1
START=$(get_time)
docker compose up -d $SERVICES > /dev/null 2>&1
until curl -sf http://localhost:8080/health > /dev/null 2>&1; do sleep 0.5; done
END=$(get_time)
RESULTS[warm]=$(calc_duration "$START" "$END")
if check_target "${RESULTS[warm]}" "$TARGET_WARM"; then
    STATUS[warm]="PASS"
    echo -e "${GREEN}${RESULTS[warm]}s${RESET}"
else
    STATUS[warm]="FAIL"
    FAILED=1
    echo -e "${RED}${RESULTS[warm]}s (FAILED)${RESET}"
fi

# First API call benchmark
echo -n "Running first API call benchmark... "
START=$(get_time)
curl -sf -X POST http://localhost:8080/api/v1/invites \
    -H "Content-Type: application/json" \
    -d '{"email":"benchmark@stoa.dev","company":"Benchmark","source":"oss-killer-bench"}' > /dev/null
END=$(get_time)
RESULTS[api]=$(calc_duration "$START" "$END")
if check_target "${RESULTS[api]}" "$TARGET_API"; then
    STATUS[api]="PASS"
    echo -e "${GREEN}${RESULTS[api]}s${RESET}"
else
    STATUS[api]="FAIL"
    FAILED=1
    echo -e "${RED}${RESULTS[api]}s (FAILED)${RESET}"
fi

# Results table
echo ""
echo "## Benchmark Results"
echo ""
echo "| Metric | Result | Target | Status |"
echo "|--------|--------|--------|--------|"
echo "| Cold start | ${RESULTS[cold]}s | < ${TARGET_COLD}s | ${STATUS[cold]} |"
echo "| Warm start | ${RESULTS[warm]}s | < ${TARGET_WARM}s | ${STATUS[warm]} |"
echo "| First API | ${RESULTS[api]}s | < ${TARGET_API}s | ${STATUS[api]} |"
echo ""

# Summary
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All benchmarks passed!${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}Some benchmarks failed!${RESET}"
    exit 1
fi
