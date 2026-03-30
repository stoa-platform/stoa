#!/usr/bin/env bash
# =============================================================================
# Service Port Drift Detection — Cross-repo port consistency check
# =============================================================================
# Post-mortem PR #2077: Console UI was unreachable because nginx backend URL
# pointed to port 80 while the K8s Service (Helm chart in stoa-infra) exposed
# port 8000. The drift existed since January 2026 but was never caught.
#
# This script validates that *_BACKEND_URL / *_URL env vars in k8s manifests
# and Helm chart defaults use the correct ports for each service.
#
# Usage: ./scripts/ci/check-service-ports.sh [--verbose]
#
# Exit codes:
#   0 — all ports match
#   1 — port mismatches found
# =============================================================================
set -euo pipefail

VERBOSE="${1:-}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ERRORS=0
CHECKED=0

# ---------------------------------------------------------------------------
# Known-ports map — source of truth
# These are the ports that K8s Services ACTUALLY expose (from stoa-infra Helm).
# Update this list when a Service port changes in stoa-infra.
# Format: "service_name:expected_port" per line
# ---------------------------------------------------------------------------
KNOWN_PORTS="
stoa-control-plane-api:8000
stoa-gateway:80
opensearch-dashboards:5601
grafana:3000
prometheus-kube-prometheus-prometheus:9090
"

# Lookup expected port for a service name. Returns empty if not found.
get_expected_port() {
  echo "$KNOWN_PORTS" | grep "^${1}:" | cut -d: -f2 || true
}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_ok() { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
log_err() { printf "  ${RED}✗${NC} %s\n" "$1"; ERRORS=$((ERRORS + 1)); }
log_warn() { printf "  ${YELLOW}!${NC} %s\n" "$1"; }
log_verbose() { if [[ "$VERBOSE" == "--verbose" ]]; then printf "    %s\n" "$1"; fi; }

# ---------------------------------------------------------------------------
# extract_urls_from_yaml <file>
# Extracts lines with internal K8s service URLs (*.svc.cluster.local).
# Outputs: ENV_VAR_NAME|URL|LINENO (one per line)
# Uses a temp file to avoid subshell variable loss in bash 3.2.
# ---------------------------------------------------------------------------
extract_urls_from_yaml() {
  local file="$1"
  local tmpfile
  tmpfile=$(mktemp)

  grep -n 'value:.*://.*\.svc\.cluster\.local' "$file" 2>/dev/null > "$tmpfile" || true

  while IFS= read -r line; do
    local lineno url
    lineno=$(echo "$line" | cut -d: -f1)

    # Extract the URL — handle plain YAML and Helm template defaults
    if echo "$line" | grep -q '| default'; then
      url=$(echo "$line" | sed -E 's/.*\| default "([^"]+)".*/\1/')
    else
      url=$(echo "$line" | grep -oE 'https?://[^"| ]+' | head -1)
    fi

    # Get the env var name from the preceding line
    local env_name
    env_name=$(sed -n "$((lineno - 1))p" "$file" | grep -oE 'name: *[A-Z_]+' | sed 's/name: *//' || echo "UNKNOWN")

    if [[ -n "$url" ]]; then
      echo "${env_name}|${url}|${lineno}"
    fi
  done < "$tmpfile"

  rm -f "$tmpfile"
}

# ---------------------------------------------------------------------------
# check_port <file> <env_name> <url> <lineno>
# Validates the port in the URL against the known-ports map.
# ---------------------------------------------------------------------------
check_port() {
  local file="$1" env_name="$2" url="$3" lineno="$4"
  local host port service_name expected

  # Extract host and port from URL
  host=$(echo "$url" | sed -E 's|https?://||' | sed -E 's|/.*||' | sed -E 's|:[0-9]+$||')
  port=$(echo "$url" | grep -oE ':[0-9]+' | tail -1 | tr -d ':')

  if [[ -z "$port" ]]; then
    log_verbose "Skipping ${env_name} — no explicit port in URL"
    return
  fi

  # Extract service name (first component of the hostname)
  service_name=$(echo "$host" | cut -d. -f1)

  CHECKED=$((CHECKED + 1))

  expected=$(get_expected_port "$service_name")
  if [[ -n "$expected" ]]; then
    if [[ "$port" != "$expected" ]]; then
      log_err "${file}:${lineno} — ${env_name}: port ${port} != expected ${expected} (service: ${service_name})"
    else
      log_ok "${env_name}: port ${port} matches ${service_name}"
    fi
  else
    log_warn "${env_name}: service '${service_name}' not in known-ports map (port: ${port})"
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "=== Service Port Drift Detection ==="
echo ""

RESULTS_FILE=$(mktemp)
FILES_FILE=$(mktemp)
trap 'rm -f "$RESULTS_FILE" "$FILES_FILE"' EXIT

# 1. Scan k8s deployment manifests (exclude worktrees and archive)
echo "Scanning k8s deployment manifests..."
find "$REPO_ROOT" -path "*/k8s/deployment.yaml" -type f > "$FILES_FILE"
while IFS= read -r file; do
  # Skip worktrees and archive directories
  [[ "$file" == *".claude/worktrees"* ]] && continue
  [[ "$file" == *"/archive/"* ]] && continue

  local_path="${file#"$REPO_ROOT"/}"
  log_verbose "Checking ${local_path}"

  extract_urls_from_yaml "$file" > "$RESULTS_FILE"
  while IFS='|' read -r env_name url lineno; do
    [[ -z "$env_name" ]] && continue
    check_port "$local_path" "$env_name" "$url" "$lineno"
  done < "$RESULTS_FILE"
done < "$FILES_FILE"

echo ""

# 2. Scan Helm chart templates
echo "Scanning Helm chart templates..."
find "$REPO_ROOT/charts" -name "*.yaml" -type f 2>/dev/null > "$FILES_FILE"
while IFS= read -r file; do
  local_path="${file#"$REPO_ROOT"/}"
  log_verbose "Checking ${local_path}"

  extract_urls_from_yaml "$file" > "$RESULTS_FILE"
  while IFS='|' read -r env_name url lineno; do
    [[ -z "$env_name" ]] && continue
    check_port "$local_path" "$env_name" "$url" "$lineno"
  done < "$RESULTS_FILE"
done < "$FILES_FILE"

echo ""

# 3. Summary
echo "=== Summary ==="
echo "  Checked: ${CHECKED} URLs"
if [[ "$ERRORS" -gt 0 ]]; then
  printf "  ${RED}Failed: ${ERRORS} port mismatch(es)${NC}\n"
  echo ""
  echo "Fix: update the URL port to match the known-ports map in this script."
  echo "If the Service port changed in stoa-infra, update KNOWN_PORTS in this script."
  exit 1
else
  printf "  ${GREEN}All ports match.${NC}\n"
  exit 0
fi
