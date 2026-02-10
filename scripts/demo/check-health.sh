#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Docker Compose Health Check
# =============================================================================
# Verifies all services are running and healthy after `docker compose up`.
#
# Usage:
#   ./scripts/demo/check-health.sh                  # Check all services
#   ./scripts/demo/check-health.sh --wait           # Wait until all healthy (max 5 min)
#   ./scripts/demo/check-health.sh --federation     # Include federation services
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/../../deploy/docker-compose" && pwd)"
WAIT_MODE="${WAIT_MODE:-false}"
FEDERATION="${FEDERATION:-false}"
MAX_WAIT="${MAX_WAIT:-300}"

for arg in "$@"; do
  case $arg in
    --wait)       WAIT_MODE=true ;;
    --federation) FEDERATION=true ;;
    --help|-h)
      echo "Usage: $0 [--wait] [--federation]"
      echo ""
      echo "  --wait        Wait until all services are healthy (max ${MAX_WAIT}s)"
      echo "  --federation  Include federation profile services"
      exit 0
      ;;
  esac
done

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Base services (expected to be running and healthy)
BASE_SERVICES=(
  "stoa-postgres"
  "stoa-keycloak"
  "stoa-api"
  "stoa-console"
  "stoa-portal"
  "stoa-gateway"
  "stoa-proxy"
  "stoa-prometheus"
  "stoa-grafana"
  "stoa-loki"
  "stoa-promtail"
  "stoa-alertmanager"
  "stoa-opensearch"
  "stoa-opensearch-dashboards"
)

# One-shot services (expected to have exited successfully)
ONESHOT_SERVICES=(
  "stoa-db-migrate"
  "stoa-opensearch-init"
)

# Federation profile services
FEDERATION_SERVICES=(
  "stoa-federation-ldap"
  "stoa-federation-gateway"
)

check_service() {
  local name="$1"
  local expected_type="${2:-running}"

  # Get container status
  local status
  status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null) || {
    echo -e "  ${RED}MISSING${NC}  $name"
    return 1
  }

  if [ "$expected_type" = "oneshot" ]; then
    local exit_code
    exit_code=$(docker inspect --format='{{.State.ExitCode}}' "$name" 2>/dev/null) || exit_code="?"
    if [ "$status" = "exited" ] && [ "$exit_code" = "0" ]; then
      echo -e "  ${GREEN}DONE${NC}     $name (exited 0)"
      return 0
    else
      echo -e "  ${RED}FAIL${NC}     $name (status=$status, exit=$exit_code)"
      return 1
    fi
  fi

  # Running service — check health
  local health
  health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$name" 2>/dev/null) || health="unknown"

  if [ "$health" = "healthy" ]; then
    echo -e "  ${GREEN}HEALTHY${NC}  $name"
    return 0
  elif [ "$health" = "starting" ]; then
    echo -e "  ${YELLOW}STARTING${NC} $name"
    return 1
  elif [ "$status" = "running" ] && [ "$health" = "no-healthcheck" ]; then
    echo -e "  ${BLUE}RUNNING${NC}  $name (no healthcheck)"
    return 0
  else
    echo -e "  ${RED}UNHEALTHY${NC} $name (status=$status, health=$health)"
    return 1
  fi
}

run_check() {
  local failed=0

  echo ""
  echo "================================================================"
  echo "  STOA Platform — Service Health Check"
  echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "================================================================"
  echo ""

  echo -e "${BLUE}Base Services (${#BASE_SERVICES[@]}):${NC}"
  for svc in "${BASE_SERVICES[@]}"; do
    check_service "$svc" "running" || failed=$((failed + 1))
  done

  echo ""
  echo -e "${BLUE}One-Shot Services (${#ONESHOT_SERVICES[@]}):${NC}"
  for svc in "${ONESHOT_SERVICES[@]}"; do
    check_service "$svc" "oneshot" || failed=$((failed + 1))
  done

  if [ "$FEDERATION" = true ]; then
    echo ""
    echo -e "${BLUE}Federation Services (${#FEDERATION_SERVICES[@]}):${NC}"
    for svc in "${FEDERATION_SERVICES[@]}"; do
      check_service "$svc" "running" || failed=$((failed + 1))
    done
  fi

  local total=${#BASE_SERVICES[@]}
  total=$((total + ${#ONESHOT_SERVICES[@]}))
  if [ "$FEDERATION" = true ]; then
    total=$((total + ${#FEDERATION_SERVICES[@]}))
  fi
  local passed=$((total - failed))

  echo ""
  echo "================================================================"
  echo -e "  Result: ${passed}/${total} services OK"
  if [ "$failed" -gt 0 ]; then
    echo -e "  ${RED}${failed} service(s) need attention${NC}"
  else
    echo -e "  ${GREEN}All services healthy!${NC}"
  fi
  echo "================================================================"

  echo ""
  echo -e "${BLUE}Access Points:${NC}"
  echo "  Console:      http://localhost"
  echo "  Portal:       http://localhost:3002"
  echo "  API:          http://localhost:8000"
  echo "  Gateway:      http://localhost:8081"
  echo "  Keycloak:     http://localhost/auth"
  echo "  Grafana:      http://localhost/grafana"
  echo "  STOA Logs:    http://localhost/logs"
  echo "  Prometheus:   http://localhost:9090"
  echo "  AlertManager: http://localhost:9093"

  return "$failed"
}

if [ "$WAIT_MODE" = true ]; then
  echo -e "${BLUE}Waiting for all services to be healthy (max ${MAX_WAIT}s)...${NC}"
  elapsed=0
  while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    if run_check 2>/dev/null; then
      run_check
      exit 0
    fi
    sleep 10
    elapsed=$((elapsed + 10))
    echo -e "${YELLOW}[${elapsed}s/${MAX_WAIT}s] Not all services healthy yet, retrying...${NC}"
  done
  echo -e "${RED}Timeout after ${MAX_WAIT}s. Running final check:${NC}"
  run_check
  exit 1
else
  run_check
  exit $?
fi
