#!/usr/bin/env bash
# After a stoa-gateway pod restart, routes live only in process memory.
# GET /apis/<tenant>/<name>/... is 404 until stoactl publishes the same
# contracts again. There is no disk replay.
#
# stoactl (stoa-v2) is the publisher. It POSTs each contract to
# http://stoa-gateway-admin.stoa.svc:8080/admin/contracts with the admin
# bearer, inboundAuth=jwt, and an audience (route or STOA_JWT_AUDIENCE).
# This script prints that call. With --post it sends the same JSON.
# It does not run kubectl, ssh, or docker, and it does not touch a registry.
#
#   deploy/standalone/republish-contracts.sh contracts/*.json
#   STOA_ADMIN_API_TOKEN=... STOA_GATEWAY_ADMIN_URL=http://stoa-gateway-admin.stoa.svc:8080 \
#     deploy/standalone/republish-contracts.sh --post contracts/*.json
#   deploy/standalone/republish-contracts.sh --self-test
set -euo pipefail

admin_url="${STOA_GATEWAY_ADMIN_URL:-http://stoa-gateway-admin.stoa.svc:8080}"
admin_url="${admin_url%/}"
mode="print"

usage() {
  echo "usage: republish-contracts.sh [--print|--post|--self-test] contract.json ..." >&2
  exit 2
}

if [[ "${1:-}" == "--print" || "${1:-}" == "--post" || "${1:-}" == "--self-test" ]]; then
  mode="${1#--}"
  shift
fi

check_contract() {
  local file="$1"
  python3 - "$file" <<'PY'
import json, re, sys
path = sys.argv[1]
doc = json.load(open(path))
auth = str(doc.get("inboundAuth") or "").strip().lower()
if not re.fullmatch(r"jwt|bearer|oauth2|oidc|client_credentials|jwt_validation", auth):
    sys.stderr.write(f"{path}: inboundAuth must be jwt (standalone rejects an open contract)\n")
    sys.exit(1)
PY
}

print_plan() {
  local file="$1"
  echo "GET /apis/<tenant>/<name>/... is 404 until this contract is published again"
  echo "stoactl posts the same body. Equivalent call (ClusterIP, no Ingress headers):"
  echo "curl -sS -X POST ${admin_url}/admin/contracts \\"
  echo "  -H \"authorization: Bearer \$STOA_ADMIN_API_TOKEN\" \\"
  echo "  -H 'content-type: application/json' \\"
  echo "  --data-binary @${file}"
  echo "POST /admin/apis and DELETE /admin/policies stay 403 in standalone."
}

post_one() {
  local file="$1"
  local token="${STOA_ADMIN_API_TOKEN:-}"
  if [[ -z "$token" ]]; then
    echo "STOA_ADMIN_API_TOKEN is required for --post" >&2
    exit 2
  fi
  local code
  code="$(curl -sS -o /tmp/stoa-republish-body -w '%{http_code}' \
    -X POST "${admin_url}/admin/contracts" \
    -H "authorization: Bearer ${token}" \
    -H 'content-type: application/json' \
    --data-binary @"${file}")"
  echo "${file} -> ${code} $(cat /tmp/stoa-republish-body)"
  if [[ "$code" != "200" && "$code" != "201" ]]; then
    exit 1
  fi
}

self_test() {
  local tmp
  tmp="$(mktemp -d)"
  printf '%s\n' '{"name":"live-api","inboundAuth":"jwt","tenant_id":"demo"}' > "$tmp/ok.json"
  printf '%s\n' '{"name":"open-api","tenant_id":"demo"}' > "$tmp/open.json"
  local out
  out="$(bash "$0" --print "$tmp/ok.json")"
  grep -q '404' <<<"$out"
  grep -q '/admin/contracts' <<<"$out"
  grep -q 'POST /admin/apis' <<<"$out"
  if bash "$0" --print "$tmp/open.json" >/dev/null 2>"$tmp/err"; then
    echo "open contract was accepted" >&2
    exit 1
  fi
  grep -q 'inboundAuth' "$tmp/err"
  if grep -E -q '(^|[[:space:]])(kubectl|ssh|docker)([[:space:]]|$)' "$0"; then
    # Comments may name those tools. The executable lines must not invoke them.
    if grep -E -v '^[[:space:]]*#' "$0" | grep -E -q '(^|[[:space:];|&])(kubectl|ssh|docker)([[:space:]]|$)'; then
      echo "script invokes kubectl, ssh, or docker" >&2
      exit 1
    fi
  fi
  rm -rf "$tmp"
  echo "republish-contracts self-test ok"
}

if [[ "$mode" == "self-test" ]]; then
  self_test
  exit 0
fi

if [[ "$#" -lt 1 ]]; then
  usage
fi

for file in "$@"; do
  if [[ ! -f "$file" ]]; then
    echo "not a file: $file" >&2
    exit 2
  fi
  check_contract "$file"
  if [[ "$mode" == "post" ]]; then
    post_one "$file"
  else
    print_plan "$file"
  fi
done
