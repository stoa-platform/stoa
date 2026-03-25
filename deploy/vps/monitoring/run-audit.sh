#!/usr/bin/env bash
# Run fleet-wide VPS audit: SSH into each VPS, collect system data, produce SUMMARY.md
#
# Usage: ./run-audit.sh [--only LABEL] [--timeout SECONDS]
#
# Reads: deploy/vps/monitoring/vps-list.txt
# Writes: ./audit-results/SUMMARY.md + per-host raw files
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIT_SCRIPT="${SCRIPT_DIR}/audit-vps.sh"
VPS_LIST="${SCRIPT_DIR}/vps-list.txt"
SSH_KEY=~/.ssh/id_ed25519_stoa
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -i $SSH_KEY"
RESULTS_DIR="./audit-results"
TIMEOUT=30
ONLY_LABEL=""

# --- Parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) ONLY_LABEL="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) echo "Usage: $0 [--only LABEL] [--timeout SECONDS]"; exit 1 ;;
  esac
done

# --- Colors ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[-]${NC} $*"; }

# --- Validate inputs ---
if [[ ! -f "$VPS_LIST" ]]; then
  err "VPS list not found: ${VPS_LIST}"
  err "Create it with format: IP|SSH_USER|LABEL|ROLE"
  exit 1
fi

if [[ ! -f "$AUDIT_SCRIPT" ]]; then
  err "Audit script not found: ${AUDIT_SCRIPT}"
  exit 1
fi

mkdir -p "$RESULTS_DIR"

# --- Read VPS list ---
declare -a HOSTS=()
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  HOSTS+=("$line")
done < "$VPS_LIST"

log "Fleet Audit — ${#HOSTS[@]} VPS from ${VPS_LIST}"
log "Results → ${RESULTS_DIR}/"
echo ""

# --- Audit each host ---
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SUCCESS=0
FAILED=0
WARNINGS=0

for entry in "${HOSTS[@]}"; do
  IFS='|' read -r ip user label role <<< "$entry"

  if [[ -n "$ONLY_LABEL" && "$label" != "$ONLY_LABEL" ]]; then
    continue
  fi

  echo -e "${CYAN}--- ${label} (${user}@${ip}) ---${NC}"

  RAW_FILE="${RESULTS_DIR}/${label}.txt"

  # SSH + run audit script remotely (no `timeout` on macOS — ConnectTimeout in SSH_OPTS handles it)
  if ssh $SSH_OPTS -o "ServerAliveInterval=5" -o "ServerAliveCountMax=$((TIMEOUT/5))" "${user}@${ip}" "bash -s" < "$AUDIT_SCRIPT" > "$RAW_FILE" 2>/dev/null; then
    log "OK — $(wc -l < "$RAW_FILE" | tr -d ' ') lines collected"
    ((SUCCESS++))

    # Quick checks for warnings
    if grep -q "disk_warn=" "$RAW_FILE"; then
      warn "Disk usage high: $(grep 'disk_warn=' "$RAW_FILE" | sed 's/disk_warn=//')"
      ((WARNINGS++))
    fi
    if grep -q "unattended_upgrades=missing" "$RAW_FILE"; then
      warn "unattended-upgrades not installed"
      ((WARNINGS++))
    fi
    if grep -q "fail2ban=missing" "$RAW_FILE"; then
      warn "fail2ban not installed"
      ((WARNINGS++))
    fi
    if grep -q "ssh_password_auth=yes" "$RAW_FILE"; then
      warn "SSH password auth enabled"
      ((WARNINGS++))
    fi
  else
    err "FAILED — SSH timeout or error"
    echo "UNREACHABLE" > "$RAW_FILE"
    ((FAILED++))
  fi
  echo ""
done

# --- Generate SUMMARY.md ---
SUMMARY="${RESULTS_DIR}/SUMMARY.md"

cat > "$SUMMARY" << HEADER
# VPS Fleet Audit

**Date**: ${TIMESTAMP}
**Hosts**: ${#HOSTS[@]} total — ${SUCCESS} OK, ${FAILED} unreachable
**Warnings**: ${WARNINGS}

## Fleet Overview

| Host | IP | Role | OS | Uptime | CPU | RAM | Disk | Docker |
|------|----|------|----|--------|-----|-----|------|--------|
HEADER

for entry in "${HOSTS[@]}"; do
  IFS='|' read -r ip user label role <<< "$entry"
  RAW="${RESULTS_DIR}/${label}.txt"

  if [[ ! -f "$RAW" ]] || grep -q "UNREACHABLE" "$RAW"; then
    echo "| ${label} | ${ip} | ${role} | - | - | - | - | - | - |" >> "$SUMMARY"
    continue
  fi

  # Extract values
  get() { grep "^$1=" "$RAW" 2>/dev/null | head -1 | cut -d= -f2- || echo "-"; }

  os=$(get os)
  uptime=$(get uptime_days)
  cpus=$(get cpus)
  ram_pct=$(get ram_pct)
  disk_pct=$(get disk_pct)
  containers=$(get docker_containers)

  [[ "$uptime" != "-" ]] && uptime="${uptime}d"
  [[ "$containers" != "-" ]] && containers="${containers} ctr"

  echo "| ${label} | \`${ip}\` | ${role} | ${os} | ${uptime} | ${cpus} | ${ram_pct} | ${disk_pct} | ${containers} |" >> "$SUMMARY"
done

# --- Security section ---
cat >> "$SUMMARY" << 'SEC_HEADER'

## Security Posture

| Host | Fail2ban | Unattended | SSH Root | SSH Password | Firewall |
|------|----------|------------|----------|-------------|----------|
SEC_HEADER

for entry in "${HOSTS[@]}"; do
  IFS='|' read -r ip user label role <<< "$entry"
  RAW="${RESULTS_DIR}/${label}.txt"

  if [[ ! -f "$RAW" ]] || grep -q "UNREACHABLE" "$RAW"; then
    echo "| ${label} | - | - | - | - | - |" >> "$SUMMARY"
    continue
  fi

  get() { grep "^$1=" "$RAW" 2>/dev/null | head -1 | cut -d= -f2- || echo "-"; }

  f2b=$(get fail2ban)
  uu=$(get unattended_upgrades)
  root_login=$(get ssh_root_login)
  pw_auth=$(get ssh_password_auth)
  fw=$(get firewall)

  echo "| ${label} | ${f2b} | ${uu} | ${root_login} | ${pw_auth} | ${fw} |" >> "$SUMMARY"
done

# --- Docker section ---
cat >> "$SUMMARY" << 'DOCKER_HEADER'

## Docker Containers

DOCKER_HEADER

for entry in "${HOSTS[@]}"; do
  IFS='|' read -r ip user label role <<< "$entry"
  RAW="${RESULTS_DIR}/${label}.txt"

  if [[ ! -f "$RAW" ]] || grep -q "UNREACHABLE" "$RAW"; then
    continue
  fi

  containers=$(grep "^docker_containers=" "$RAW" 2>/dev/null | cut -d= -f2-)
  if [[ -z "$containers" || "$containers" == "0" ]]; then
    continue
  fi

  echo "### ${label}" >> "$SUMMARY"
  echo "" >> "$SUMMARY"
  echo '```' >> "$SUMMARY"
  # Extract docker_ps block
  sed -n '/^docker_ps<<EOF$/,/^EOF$/p' "$RAW" | grep -v '^docker_ps<<EOF$\|^EOF$' >> "$SUMMARY"
  echo '```' >> "$SUMMARY"
  echo "" >> "$SUMMARY"
done

# --- Disk warnings ---
DISK_WARNS=""
for entry in "${HOSTS[@]}"; do
  IFS='|' read -r ip user label role <<< "$entry"
  RAW="${RESULTS_DIR}/${label}.txt"
  [[ ! -f "$RAW" ]] && continue
  while IFS= read -r line; do
    DISK_WARNS+="- **${label}**: ${line#disk_warn=}\n"
  done < <(grep "^disk_warn=" "$RAW" 2>/dev/null || true)
done

if [[ -n "$DISK_WARNS" ]]; then
  cat >> "$SUMMARY" << 'DISK_HEADER'
## Disk Warnings

DISK_HEADER
  echo -e "$DISK_WARNS" >> "$SUMMARY"
fi

# --- Updates section ---
cat >> "$SUMMARY" << 'UPD_HEADER'

## Pending Updates

| Host | Pending | Security | Last Update |
|------|---------|----------|-------------|
UPD_HEADER

for entry in "${HOSTS[@]}"; do
  IFS='|' read -r ip user label role <<< "$entry"
  RAW="${RESULTS_DIR}/${label}.txt"

  if [[ ! -f "$RAW" ]] || grep -q "UNREACHABLE" "$RAW"; then
    echo "| ${label} | - | - | - |" >> "$SUMMARY"
    continue
  fi

  get() { grep "^$1=" "$RAW" 2>/dev/null | head -1 | cut -d= -f2- || echo "-"; }

  pending=$(get pending_updates)
  security=$(get pending_security)
  last=$(get apt_last_update)
  [[ "$last" == "-" ]] && last=$(get apt_cache_age)

  echo "| ${label} | ${pending} | ${security} | ${last} |" >> "$SUMMARY"
done

echo "" >> "$SUMMARY"
echo "---" >> "$SUMMARY"
echo "*Generated by \`run-audit.sh\` on ${TIMESTAMP}*" >> "$SUMMARY"

# --- Final report ---
echo ""
echo "========================================"
echo -e "  ${GREEN}OK${NC}: ${SUCCESS}   ${RED}FAIL${NC}: ${FAILED}   ${YELLOW}WARNINGS${NC}: ${WARNINGS}"
echo "========================================"
echo ""
log "Summary: ${SUMMARY}"
log "Raw data: ${RESULTS_DIR}/<label>.txt"
