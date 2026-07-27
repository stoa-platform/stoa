#!/usr/bin/env bash
# =============================================================================
# STOA Platform — VPS Inventory
# =============================================================================
# Source of truth for the VPS fleet. All deploy scripts MUST source this file
# instead of hardcoding IPs and SSH keys.
#
# Usage:
#   source "$(dirname "$0")/vps-inventory.sh"
#   ssh_to worker-3 "docker ps"
#   for_each_vps "uptime"
#   vps_verify                      # probe every entry; non-zero exit on drift
#
# -----------------------------------------------------------------------------
# LAST RECONCILED WITH REALITY: 2026-07-27 (every entry probed live).
#
# The previous revision claimed to be the source of truth while describing six
# VPS, none of which matched the running estate, and omitting the five Contabo
# hosts that actually carry the platform. It also aborted on `source` unless six
# env vars were set (`${VAR:?}`), which is why nobody noticed it had rotted.
#
# Both faults are fixed here: the real fleet is unconditional, everything else is
# optional and cannot break sourcing. Run `vps_verify` before trusting this file
# — it exits non-zero when the fleet diverges from what is written below.
# =============================================================================

# --- SSH key (per-device, overridable via env) -------------------------------
STOA_SSH_KEY="${STOA_SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"

# --- stoa-infra checkout ------------------------------------------------------
# Consumed by distribute-ssh-key.sh ($STOA_INFRA_DIR/deploy/vps/hegemon/workers.txt).
# Defined here because nothing else defined it: under `set -u` the consumer
# aborted on the unbound variable. The workers.txt mechanism is now redundant —
# the five workers are first-class entries below — but the path stays valid.
STOA_INFRA_DIR="${STOA_INFRA_DIR:-$HOME/stoa-platform/stoa-infra}"

# =============================================================================
# Fleet
# =============================================================================
# Format: NAME|SSH_DEST|USER|PURPOSE
#
# SSH_DEST is an ~/.ssh/config ALIAS, not an IP. Two reasons: no addresses in Git
# (same intent as the env-var indirection below; the gitleaks allowlist only
# tolerates IPs under deploy/vps/), and the alias already carries HostName, User
# and IdentityFile. `ssh user@alias` resolves correctly, so the field stays
# drop-in compatible with consumers that build "${user}@${ip}".

# --- Contabo — the estate that actually runs the platform --------------------
# 5 identical VPS: 8 vCPU AMD EPYC, 24 GB RAM, 400 GB SSD, 8 GB swap, Debian 12.
# Total 40 vCPU / 120 GB / 2 TB. Measured CPU steal: 0 ticks on all five.
# All five run claude-watchdog.service (HEGEMON agents) and node_exporter.
VPS_FLEET=(
  "worker-1|worker-1|hegemon|Contabo — IDLE (~23 GB free). fsync p99 10.0 ms"
  "worker-2|worker-2|hegemon|Contabo — IDLE. Best measured disk (fsync p99 9.6 ms)"
  "worker-3|worker-3|hegemon|Contabo — k3s agent + cluster ingress entrypoint; webMethods 10.15 + Elasticsearch (Docker); Caddy; vault-agent; stoa-connect-dev"
  "worker-4|worker-4|hegemon|Contabo — IDLE. fsync p99 10.9 ms"
  "worker-5|worker-5|hegemon|Contabo — k3s CONTROL-PLANE (v1.34.5, SQLite/kine)"
)

# Disk note (fio, 2026-07-27, roles ansible/fleet_disk_bench in stoa-labs):
# fsync p99 sits ON the etcd 10 ms limit across identical idle nodes, with a
# p99.9 of 18-24 ms. Embedded-etcd HA on 3 nodes is therefore ruled out; the
# single control-plane on SQLite/kine above is the deliberate topology, backed by
# rebuild-from-Git rather than by consensus.

# --- Other hosts, appended only when their address is provided ---------------
# Never use ${VAR:?} here: one unset variable must not abort every consumer.
_vps_add_optional() {
  if [ -n "${2:-}" ]; then VPS_FLEET+=("$1|$2|$3|$4"); fi
  return 0
}

# n8n — LIVE (probed 2026-07-27). n8n.gostoa.dev returns HTTP/2 200 and serves
# the n8n UI behind a valid Let's Encrypt cert (CN=n8n.gostoa.dev, expires
# 2026-10-02). The cert is issued to the ORIGIN, so Cloudflare proxying is OFF
# and the instance is directly exposed to the internet. Not reachable with
# STOA_SSH_KEY — credentials unknown, so it is unmanaged from here.
_vps_add_optional n8n-vps "${VPS_N8N_IP:-}" debian \
  "n8n + PocketBase + Healthchecks — LIVE, directly exposed, NO SSH ACCESS"

# OVH Arena-benchmark pair — port 22 answers, but STOA_SSH_KEY is refused for
# hegemon, debian and root alike. Hosts alive, outside our management.
_vps_add_optional kong-vps "${VPS_KONG_IP:-}" debian \
  "OVH — Kong (Arena benchmark) — ALIVE but SSH REFUSED, OUT OF MANAGEMENT"
_vps_add_optional gravitee-vps "${VPS_GRAVITEE_IP:-}" debian \
  "OVH — Gravitee APIM v4 (Arena benchmark) — ALIVE but SSH REFUSED, OUT OF MANAGEMENT"

# webMethods VPS (OVH) — 443 listens but the TLS handshake fails for
# vps-wm.gostoa.dev (tlsv1 alert internal error): most likely ours with an
# expired or missing certificate rather than a reassigned address. To qualify.
# NOTE: the webMethods instance actually in use is the Docker one on worker-3.
_vps_add_optional webmethods-vps "${VPS_WEBMETHODS_IP:-}" debian \
  "OVH — vps-wm.gostoa.dev, TLS BROKEN, DEGRADED — superseded by worker-3"

# Infisical — DEAD. vault.gostoa.dev still resolves but 443 is unreachable.
# Consequence worth remembering: the Cloudflare DNS token
# (shared/cloudflare/API_TOKEN, DNS:Edit) lived in this vault, so the credential
# required to delete its own dangling DNS record is locked behind the dead host.
# Effective secret store is now Vault (ADR-074).
_vps_add_optional infisical-vps "${VPS_INFISICAL_IP:-}" debian \
  "vault.gostoa.dev — DEAD, leaves a dangling DNS record"

# bench-vps — no reachable address found during reconciliation. Presumed gone.
_vps_add_optional bench-vps "${VPS_BENCH_IP:-}" debian \
  "OpenSearch bench + Arena runner — PRESUMED DECOMMISSIONED"

# --- Cloudflare Access (service token, sourced from env or the vault) --------
# NOT a DNS API token: these authenticate to Access-protected apps and cannot
# write to the zone. Empty = no CF Access headers sent (backward compatible).
CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"

# --- Infisical ----------------------------------------------------------------
# Kept for API compatibility with existing callers. The host is DOWN as of
# 2026-07-27: every infisical_curl call will fail to connect.
INFISICAL_URL="${INFISICAL_URL:-https://vault.gostoa.dev}"
INFISICAL_PROJECT_ID="${INFISICAL_PROJECT_ID:-97972ffc-990b-4d28-9c4d-0664d217f03b}"

# =============================================================================
# Helper functions
# =============================================================================

# Get a VPS field by name: vps_get worker-3 dest → the SSH destination.
# 'ip' is accepted as a synonym of 'dest' for backward compatibility.
vps_get() {
  local name="$1" field="$2"
  for entry in "${VPS_FLEET[@]}"; do
    IFS='|' read -r n dest user purpose <<< "$entry"
    if [ "$n" = "$name" ]; then
      case "$field" in
        ip|dest) echo "$dest" ;;
        user)    echo "$user" ;;
        purpose) echo "$purpose" ;;
        *)       echo "Unknown field: $field" >&2; return 1 ;;
      esac
      return 0
    fi
  done
  echo "Unknown VPS: $name" >&2
  return 1
}

# List every entry name: vps_names
vps_names() {
  local entry n rest
  for entry in "${VPS_FLEET[@]}"; do
    IFS='|' read -r n rest <<< "$entry"
    echo "$n"
  done
}

# SSH to a named VPS: ssh_to worker-3 "docker ps"
ssh_to() {
  local name="$1"; shift
  local dest user
  dest=$(vps_get "$name" dest) || return 1
  user=$(vps_get "$name" user) || return 1
  ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${dest}" "$@"
}

# SCP to a named VPS: scp_to worker-3 local_file remote_path
scp_to() {
  local name="$1" local_file="$2" remote_path="$3"
  local dest user
  dest=$(vps_get "$name" dest) || return 1
  user=$(vps_get "$name" user) || return 1
  scp -i "$STOA_SSH_KEY" "$local_file" "${user}@${dest}:${remote_path}"
}

# Run a command on every VPS: for_each_vps "uptime"
for_each_vps() {
  local cmd="$1"
  for entry in "${VPS_FLEET[@]}"; do
    IFS='|' read -r name dest user purpose <<< "$entry"
    echo "=== $name ($dest) ==="
    ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${dest}" "$cmd" 2>&1 \
      || echo "[FAIL] $name unreachable"
    echo ""
  done
}

# Probe every entry and report divergence. Read-only: runs `true` remotely.
# Exits non-zero if any entry is unreachable — so CI or a pre-deploy hook can
# fail instead of letting this file rot unnoticed again. Entries documented as
# unmanaged (NO SSH ACCESS / OUT OF MANAGEMENT / DEAD / PRESUMED) are expected
# to fail and are reported as KNOWN, not as drift.
vps_verify() {
  local rc=0 entry name dest user purpose
  printf '%-16s %-14s %-12s %s\n' NAME DEST STATUS NOTE
  printf '%.0s-' {1..78}; echo
  for entry in "${VPS_FLEET[@]}"; do
    IFS='|' read -r name dest user purpose <<< "$entry"
    if ssh -i "$STOA_SSH_KEY" -o BatchMode=yes -o ConnectTimeout=10 \
         -o StrictHostKeyChecking=accept-new "${user}@${dest}" true 2>/dev/null; then
      printf '%-16s %-14s %-12s\n' "$name" "$dest" "OK"
    elif printf '%s' "$purpose" | grep -qE "NO SSH ACCESS|OUT OF MANAGEMENT|DEAD|PRESUMED|DEGRADED"; then
      printf '%-16s %-14s %-12s %s\n' "$name" "$dest" "KNOWN" "unreachable as documented"
    else
      printf '%-16s %-14s %-12s %s\n' "$name" "$dest" "DRIFT" "expected reachable"
      rc=1
    fi
  done
  if [ $rc -ne 0 ]; then
    echo "" >&2
    echo "vps_verify: the fleet diverges from this inventory." >&2
    echo "Reconcile scripts/ops/vps-inventory.sh before deploying." >&2
  fi
  return $rc
}

# Build curl headers for Infisical (CF Access + Bearer)
# Usage: infisical_curl_headers "$INFISICAL_TOKEN" → array of -H flags
infisical_curl_headers() {
  local token="${1:-$INFISICAL_TOKEN}"
  local headers=(-H "Authorization: Bearer ${token}" -H "Content-Type: application/json")
  if [ -n "$CF_ACCESS_CLIENT_ID" ] && [ -n "$CF_ACCESS_CLIENT_SECRET" ]; then
    headers+=(-H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}")
    headers+=(-H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}")
  fi
  echo "${headers[@]}"
}

# Curl wrapper for the Infisical API with CF Access headers.
# Usage: infisical_curl GET "/api/v3/secrets/raw?..." "$INFISICAL_TOKEN"
# WARNING: the Infisical host is down as of 2026-07-27 — expect connection errors.
infisical_curl() {
  local method="$1" path="$2" token="${3:-${INFISICAL_TOKEN:-}}"
  local -a headers=(-H "Authorization: Bearer ${token}" -H "Content-Type: application/json")
  if [ -n "$CF_ACCESS_CLIENT_ID" ] && [ -n "$CF_ACCESS_CLIENT_SECRET" ]; then
    headers+=(-H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}")
    headers+=(-H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}")
  fi

  if [ "$#" -ge 4 ]; then
    # Has body (4th arg)
    curl -sf -X "$method" "${INFISICAL_URL}${path}" "${headers[@]}" -d "$4"
  else
    curl -sf -X "$method" "${INFISICAL_URL}${path}" "${headers[@]}"
  fi
}
