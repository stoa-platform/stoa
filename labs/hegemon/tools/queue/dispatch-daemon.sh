#!/usr/bin/env bash
# Queue Dispatch Daemon — polls queue + worker status, dispatches work.
#
# Runs on the leader machine (ORCHESTRE pane or standalone terminal).
# When a worker goes idle (no active heg-state session), the daemon
# dispatches the next matching job from the priority queue.
#
# Usage:
#   dispatch-daemon.sh [--interval 30] [--dry-run] [--once]
#
# Requires:
#   - heg-state CLI (~/.local/bin/heg-state)
#   - stoa-dispatch (~/.local/bin/stoa-dispatch)
#   - HEGEMON_REMOTE_URL + HEGEMON_REMOTE_PASSWORD (for remote-ls)
#
# Worker-to-role mapping (same as instance-dispatch.md):
#   w1=backend, w2=frontend, w3=mcp, w4=auth, w5=qa

set -euo pipefail

INTERVAL=30
DRY_RUN=false
ONCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=true; shift ;;
    --once)     ONCE=true; shift ;;
    -h|--help)
      echo "Usage: dispatch-daemon.sh [--interval 30] [--dry-run] [--once]"
      echo ""
      echo "Options:"
      echo "  --interval N  Seconds between polls (default: 30)"
      echo "  --dry-run     Log actions without dispatching"
      echo "  --once        Run one poll cycle and exit"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Locate tools
HEG_STATE="${HOME}/.local/bin/heg-state"
STOA_DISPATCH="${HOME}/.local/bin/stoa-dispatch"

if [ ! -x "$HEG_STATE" ]; then
  echo "ERROR: heg-state not found at $HEG_STATE" >&2
  exit 1
fi

_log() {
  echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*"
}

# Map worker hostnames to roles
# Format: hostname → role
# Workers are named w1-w5 in HEGEMON fleet
worker_to_role() {
  local host="$1"
  case "$host" in
    *w1*|*worker-1*) echo "backend" ;;
    *w2*|*worker-2*) echo "frontend" ;;
    *w3*|*worker-3*) echo "mcp" ;;
    *w4*|*worker-4*) echo "auth" ;;
    *w5*|*worker-5*) echo "qa" ;;
    *) echo "" ;;  # unknown host, accept any role
  esac
}

# Map role names to worker identifiers (for stoa-dispatch)
role_to_dispatch_target() {
  local role="$1"
  case "$role" in
    backend)  echo "BACKEND" ;;
    frontend) echo "FRONTEND" ;;
    mcp)      echo "MCP" ;;
    auth)     echo "AUTH" ;;
    qa)       echo "QA" ;;
    *) echo "" ;;
  esac
}

# Get idle workers from remote-ls (PocketBase)
# An idle worker = no active session, or session in paused/done state
get_idle_roles() {
  local active_roles=""

  # Get active sessions from remote
  if [ -x "$HEG_STATE" ]; then
    active_roles=$($HEG_STATE remote-ls 2>/dev/null | \
      grep -v "^INSTANCE\|^─\|^Remote\|^No " | \
      awk '$4 !~ /^(paused|done)$/ {print $2}' | \
      sort -u)
  fi

  # All possible roles
  local all_roles="backend frontend mcp auth qa"
  local idle=""

  for role in $all_roles; do
    if ! echo "$active_roles" | grep -qw "$role"; then
      idle="$idle $role"
    fi
  done

  echo "$idle"
}

dispatch_cycle() {
  local idle_roles
  idle_roles=$(get_idle_roles)

  if [ -z "$(echo "$idle_roles" | tr -d ' ')" ]; then
    _log "No idle workers"
    return
  fi

  for role in $idle_roles; do
    # Get next job matching this role (returns enriched JSON with council fields)
    local next_job
    next_job=$($HEG_STATE queue next --role "$role" --format json 2>/dev/null || echo "")

    if [ -z "$next_job" ]; then
      continue
    fi

    # Extract all fields from enriched queue job JSON
    local ticket_id job_id title score estimate mode description priority
    ticket_id=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin)['ticket_id'])" 2>/dev/null || echo "")
    job_id=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
    title=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('title',''))" 2>/dev/null || echo "")
    score=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('council_score',''))" 2>/dev/null || echo "")
    estimate=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('estimate',''))" 2>/dev/null || echo "")
    mode=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mode','ask'))" 2>/dev/null || echo "ask")
    description=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description',''))" 2>/dev/null || echo "")
    priority=$(echo "$next_job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('priority',2))" 2>/dev/null || echo "2")

    if [ -z "$ticket_id" ] || [ -z "$job_id" ]; then
      continue
    fi

    local dispatch_target
    dispatch_target=$(role_to_dispatch_target "$role")

    if [ -z "$dispatch_target" ]; then
      _log "SKIP: no dispatch target for role $role"
      continue
    fi

    # Build enriched prompt for the worker
    local worker_prompt
    worker_prompt="Travaille sur ${ticket_id}"
    [ -n "$title" ] && worker_prompt="${worker_prompt} — ${title}"
    worker_prompt="${worker_prompt}\n"
    [ -n "$score" ] && worker_prompt="${worker_prompt}Council: ${score}/10 (Go)"
    [ -n "$mode" ] && worker_prompt="${worker_prompt}, ${mode^}"
    [ -n "$estimate" ] && [ "$estimate" != "0" ] && [ "$estimate" != "None" ] && worker_prompt="${worker_prompt}, ${estimate} pts"
    worker_prompt="${worker_prompt}\n"
    if [ -n "$description" ] && [ "$description" != "None" ] && [ ${#description} -gt 5 ]; then
      # Truncate description to 500 chars for prompt
      local desc_trunc="${description:0:500}"
      worker_prompt="${worker_prompt}Description: ${desc_trunc}\n"
    fi
    worker_prompt="${worker_prompt}Consigne: Ship ≤5pts = skip plan, implement directly. >5pts = write plan first, then implement."

    # Summary for logging
    local log_summary="P${priority}"
    [ -n "$score" ] && log_summary="${log_summary}, score ${score}"
    [ -n "$mode" ] && log_summary="${log_summary}, ${mode^}"
    [ -n "$estimate" ] && [ "$estimate" != "0" ] && [ "$estimate" != "None" ] && log_summary="${log_summary}, ${estimate}pts"

    if [ "$DRY_RUN" = true ]; then
      _log "DRY-RUN: would dispatch $ticket_id (${log_summary}, job #$job_id) → $dispatch_target ($role)"
    else
      # Mark as dispatched in queue
      $HEG_STATE queue dispatch "$job_id" "$role" 2>/dev/null || true

      # Send enriched prompt to worker via stoa-dispatch (handles Council gate)
      if [ -x "$STOA_DISPATCH" ]; then
        $STOA_DISPATCH "$dispatch_target" "$(echo -e "$worker_prompt")" 2>/dev/null || {
          _log "WARN: stoa-dispatch failed for $ticket_id → $dispatch_target"
          # Mark as failed if dispatch itself failed
          $HEG_STATE queue fail "$job_id" "dispatch-failed" 2>/dev/null || true
          continue
        }
      else
        _log "WARN: stoa-dispatch not found at $STOA_DISPATCH"
        continue
      fi

      _log "DISPATCHED: $ticket_id (${log_summary}, job #$job_id) → $dispatch_target ($role)"
    fi
  done
}

# ── Main loop ────────────────────────────────────────────────────

_log "Queue dispatch daemon started (interval: ${INTERVAL}s, dry-run: ${DRY_RUN})"

if [ "$ONCE" = true ]; then
  dispatch_cycle
  exit 0
fi

while true; do
  dispatch_cycle
  sleep "$INTERVAL"
done
