#!/usr/bin/env bash
# Identity HA failover proof (static). CAB-2555.
#
# Default and --plan print the bascule that would show Keycloak still serving
# after one replica is lost. Nothing is executed: no kubectl, helm, or docker.
# --execute refuses (exit 3) until an in-repo HA topology exists to target.
#
#   deploy/keycloak/ha-proof/failover-proof.sh
#   deploy/keycloak/ha-proof/failover-proof.sh --plan
#   deploy/keycloak/ha-proof/failover-proof.sh --execute
set -euo pipefail

PROOF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY="${PROOF_DIR}/verify_static.py"

HA_STATIC=""
RETAINED_PROD_REPLICAS=""
IN_REPO_REPLICAS=""
SHARED_CACHE=""

# --- pure helpers (unit-tested; no cluster I/O) -----------------------------

# Replicas that can be lost while sessions stay on a survivor.
# $1 replicas, $2 "true" when a shared session cache is declared.
tolerated_losses() {
  local replicas="$1" shared="$2"
  if [[ "$replicas" =~ ^[0-9]+$ && "$replicas" -ge 2 && "$shared" == "true" ]]; then
    echo $((replicas - 1))
  else
    echo 0
  fi
}

# stdin: lines "READY <name> <http-status>". Prints names answering 200.
ready_names() {
  awk '$1 == "READY" && $3 == "200" { print $2 }'
}

# stdin: same shape. Prints names that are not ready.
down_names() {
  awk '$1 == "READY" && $3 != "200" { print $2 }'
}

# Succeeds when $1 and $2 are the same non-empty session id.
session_matches() {
  [[ -n "$1" && "$1" == "$2" ]]
}

# stdin: READY table. $1 session before, $2 session after, $3 stopped replica.
# Succeeds when a survivor is ready, the victim is down, and the session held.
failover_holds() {
  local before="$1" after="$2" victim="$3" table ready down
  table="$(cat)"
  ready="$(ready_names <<<"$table")"
  down="$(down_names <<<"$table")"
  [[ -n "$ready" ]] || return 1
  grep -qx "$victim" <<<"$down" || return 1
  session_matches "$before" "$after"
}

# --- report -----------------------------------------------------------------

read_report() {
  local line key value
  while IFS= read -r line; do
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      HA_STATIC) HA_STATIC="$value" ;;
      RETAINED_PROD_REPLICAS) RETAINED_PROD_REPLICAS="$value" ;;
      IN_REPO_REPLICAS) IN_REPO_REPLICAS="$value" ;;
      SHARED_CACHE) SHARED_CACHE="$value" ;;
      *) ;;
    esac
  done < <(python3 -B "$VERIFY" --shell)
  [[ "$HA_STATIC" == "pass" || "$HA_STATIC" == "fail" ]] || {
    printf 'failover-proof: verifier did not report HA_STATIC\n' >&2
    exit 1
  }
}

print_plan() {
  local tolerated
  tolerated="$(tolerated_losses "$IN_REPO_REPLICAS" "$SHARED_CACHE")"
  cat <<EOF
Bascule plan (not executed) for retained production reference keycloak.replicas=${RETAINED_PROD_REPLICAS}:
1. Require an in-repo Keycloak workload with at least 2 replicas, pod anti-affinity, a Keycloak PodDisruptionBudget, readiness and liveness probes, and a shared session cache (Infinispan plus an explicit discovery stack).
2. Observe GET /health/ready on every replica until each returns 200.
3. Open one user session and record its id.
4. Stop exactly one replica.
5. Assert at least one replica stays ready, the stopped replica is not ready, and the same session id still resolves.
6. Start that replica again and assert every replica is ready.
Current static inputs: HA_STATIC=${HA_STATIC} in_repo_replicas=${IN_REPO_REPLICAS} shared_cache=${SHARED_CACHE} tolerated_losses=${tolerated}
A tolerated_losses of 0 means this sizing does not demonstrate surviving one loss.
EOF
}

main() {
  local mode="${1:-}"
  read_report
  print_plan
  if [[ "$mode" == "--execute" ]]; then
    printf 'REFUSING live failover: HA_STATIC=%s. Live execution is disabled.\n' \
      "$HA_STATIC" >&2
    exit 3
  fi
  if [[ "$HA_STATIC" == "pass" ]]; then
    printf 'RESULT: STATIC PASS — live bascule still not run\n'
  else
    printf 'RESULT: NOT PROVEN\n'
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
