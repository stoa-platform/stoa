#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Cloudflare DNS Records for Gateway Instances
# =============================================================================
# Creates A records for all registered gateways + stoa-connect + stoa-link.
#
# Prerequisites:
#   - CF_API_TOKEN env var (Zone:DNS:Edit scope)
#   - Zone: gostoa.dev (748bf095e4882ca8e46f21837067ced8)
#
# Usage:
#   export CF_API_TOKEN="<token>"
#   ./scripts/ops/setup-gateway-dns.sh              # Create records
#   ./scripts/ops/setup-gateway-dns.sh --dry-run     # Preview only
#   ./scripts/ops/setup-gateway-dns.sh --status       # List existing records
#
# Port Convention:
#   Gateway Admin:  native ports (8001 Kong, 8083 Gravitee, 5555 webMethods)
#   stoa-connect:   :9100 (MCP bridge agent → Control Plane)
#   stoa-link:      :9200 (MCP sidecar proxy, local)
#
# DNS Convention:
#   {type}.gostoa.dev              → Gateway admin API
#   connect-{type}.gostoa.dev      → stoa-connect agent
#   link-{type}.gostoa.dev         → stoa-link sidecar
# =============================================================================

set -euo pipefail

CF_API_TOKEN="${CF_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
ZONE_ID="748bf095e4882ca8e46f21837067ced8"
CF_API="https://api.cloudflare.com/client/v4"
DRY_RUN=false
STATUS_ONLY=false

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- Gateway inventory ---
# Format: "subdomain|ip|comment"
RECORDS=(
  # Gateway admin APIs (raw IP → proper DNS)
  "kong|51.83.45.13|Kong DB-less admin API (:8001 admin, :8000 proxy)"
  "gravitee|54.36.209.237|Gravitee APIM v4 mgmt API (:8083 mgmt, :8082 proxy)"

  # stoa-connect agents (MCP bridge, port :9100)
  "connect-kong|51.83.45.13|stoa-connect on Kong VPS (:9100)"
  "connect-gravitee|54.36.209.237|stoa-connect on Gravitee VPS (:9100)"
  "connect-webmethods|51.255.201.17|stoa-connect on webMethods VPS (:9100)"

  # stoa-link sidecars (MCP proxy, port :9200)
  "link-kong|51.83.45.13|stoa-link sidecar Kong VPS (:9200)"
  "link-gravitee|54.36.209.237|stoa-link sidecar Gravitee VPS (:9200)"
  "link-webmethods|51.255.201.17|stoa-link sidecar webMethods VPS (:9200)"
)

usage() {
  echo "Usage: $0 [--dry-run|--status]"
  echo ""
  echo "  --dry-run   Preview DNS records without creating them"
  echo "  --status    List existing *.gostoa.dev A records"
  echo ""
  echo "Required env: CF_API_TOKEN (Cloudflare API token with Zone:DNS:Edit)"
  exit 1
}

# Parse args
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --status) STATUS_ONLY=true ;;
    -h|--help) usage ;;
    *) echo "Unknown arg: $arg"; usage ;;
  esac
done

[ -z "$CF_API_TOKEN" ] && {
  echo -e "${RED}CF_API_TOKEN or CLOUDFLARE_API_TOKEN must be set${NC}"
  echo "Get it from: Infisical → prod/cloudflare/API_TOKEN"
  exit 1
}

# --- Status mode: list existing records ---
if $STATUS_ONLY; then
  echo -e "${BLUE}==> Existing A records for gostoa.dev${NC}"
  curl -s "${CF_API}/zones/${ZONE_ID}/dns_records?type=A&per_page=100" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    | jq -r '.result[] | "\(.name)\t\(.content)\tproxied=\(.proxied)\tTTL=\(.ttl)"' \
    | sort \
    | column -t -s $'\t'
  echo ""
  echo -e "${BLUE}==> Existing CNAME records for gostoa.dev${NC}"
  curl -s "${CF_API}/zones/${ZONE_ID}/dns_records?type=CNAME&per_page=100" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    | jq -r '.result[] | "\(.name)\t\(.content)\tproxied=\(.proxied)\tTTL=\(.ttl)"' \
    | sort \
    | column -t -s $'\t'
  exit 0
fi

# --- Create DNS records ---
create_record() {
  local name="$1"
  local ip="$2"
  local comment="$3"
  local fqdn="${name}.gostoa.dev"

  # Check if record already exists
  EXISTING=$(curl -s "${CF_API}/zones/${ZONE_ID}/dns_records?type=A&name=${fqdn}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    | jq -r '.result | length')

  if [ "$EXISTING" -gt 0 ]; then
    EXISTING_IP=$(curl -s "${CF_API}/zones/${ZONE_ID}/dns_records?type=A&name=${fqdn}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      | jq -r '.result[0].content')
    if [ "$EXISTING_IP" = "$ip" ]; then
      echo -e "  ${YELLOW}SKIP${NC} ${fqdn} → ${ip} (already exists)"
      return 0
    else
      echo -e "  ${YELLOW}UPDATE${NC} ${fqdn}: ${EXISTING_IP} → ${ip}"
      if ! $DRY_RUN; then
        RECORD_ID=$(curl -s "${CF_API}/zones/${ZONE_ID}/dns_records?type=A&name=${fqdn}" \
          -H "Authorization: Bearer ${CF_API_TOKEN}" \
          | jq -r '.result[0].id')
        curl -s -X PATCH "${CF_API}/zones/${ZONE_ID}/dns_records/${RECORD_ID}" \
          -H "Authorization: Bearer ${CF_API_TOKEN}" \
          -H "Content-Type: application/json" \
          -d "{\"content\": \"${ip}\", \"comment\": \"${comment}\"}" \
          | jq -r 'if .success then "    OK" else "    FAIL: \(.errors[0].message)" end'
      fi
      return 0
    fi
  fi

  if $DRY_RUN; then
    echo -e "  ${BLUE}CREATE${NC} ${fqdn} → ${ip} (${comment})"
    return 0
  fi

  RESULT=$(curl -s -X POST "${CF_API}/zones/${ZONE_ID}/dns_records" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"type\": \"A\",
      \"name\": \"${name}\",
      \"content\": \"${ip}\",
      \"ttl\": 3600,
      \"proxied\": false,
      \"comment\": \"${comment}\"
    }")

  SUCCESS=$(echo "$RESULT" | jq -r '.success')
  if [ "$SUCCESS" = "true" ]; then
    echo -e "  ${GREEN}OK${NC} ${fqdn} → ${ip}"
  else
    ERROR=$(echo "$RESULT" | jq -r '.errors[0].message // "unknown error"')
    echo -e "  ${RED}FAIL${NC} ${fqdn}: ${ERROR}"
  fi
}

echo "============================================="
echo "STOA Gateway DNS Setup — gostoa.dev"
echo "============================================="
echo ""
if $DRY_RUN; then
  echo -e "${YELLOW}DRY RUN — no changes will be made${NC}"
  echo ""
fi

echo -e "${BLUE}==> Gateway Admin DNS${NC}"
for record in "${RECORDS[@]}"; do
  IFS='|' read -r name ip comment <<< "$record"
  create_record "$name" "$ip" "$comment"
done

echo ""
echo "============================================="
echo "Port Convention Reference"
echo "============================================="
echo ""
echo "  kong.gostoa.dev              :8001 (admin)  :8000 (proxy)"
echo "  gravitee.gostoa.dev          :8083 (mgmt)   :8082 (proxy)"
echo "  vps-wm.gostoa.dev           :5555 (admin)   :9072 (UI)     [webMethods, existing]"
echo ""
echo "  connect-{type}.gostoa.dev    :8090 (stoa-connect agent, Caddy → HTTPS)"
echo "  link-{type}.gostoa.dev       :9200 (stoa-link sidecar)"
echo ""
if ! $DRY_RUN; then
  echo "Verify: ./scripts/ops/setup-gateway-dns.sh --status"
fi
