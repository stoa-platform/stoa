#!/usr/bin/env bash
# dev-doctor.sh — verify local dev prereqs (binary pass/fail).
# Invoked by `make dev-doctor`. Safe to run anytime.
set -euo pipefail

PASS=0
FAIL=0

ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; printf "      \033[33m→ %s\033[0m\n" "$2"; FAIL=$((FAIL+1)); }
info() { printf "\n\033[1m%s\033[0m\n" "$1"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_TILT="$REPO_ROOT/../stoa-infra/deploy/tilt"

info "Binaries"
for bin in tilt k3d docker mkcert; do
  if command -v "$bin" >/dev/null 2>&1; then
    ok "$bin installed"
  else
    bad "$bin missing" "brew install $bin"
  fi
done

info "DNS resolution (*.stoa.local → 127.0.0.1)"
for h in console.stoa.local portal.stoa.local api.stoa.local auth.stoa.local mcp.stoa.local; do
  ip=$(dscacheutil -q host -a name "$h" 2>/dev/null | awk '/^ip_address:/ {print $2; exit}')
  if [[ "$ip" == "127.0.0.1" ]]; then
    ok "$h"
  else
    bad "$h does not resolve to 127.0.0.1 (got: ${ip:-none})" \
        "add 'address=/.stoa.local/127.0.0.1' to /opt/homebrew/etc/dnsmasq.conf and echo 'nameserver 127.0.0.1' | sudo tee /etc/resolver/stoa.local"
  fi
done

info "TLS certs (mkcert wildcard for stoa.local)"
CERT="$INFRA_TILT/certs/_wildcard.stoa.local+1.pem"
KEY="$INFRA_TILT/certs/_wildcard.stoa.local+1-key.pem"
if [[ -f "$CERT" && -f "$KEY" ]]; then
  ok "wildcard cert present in $INFRA_TILT/certs/"
else
  bad "mkcert wildcard missing" \
      "cd $INFRA_TILT/certs && mkcert '*.stoa.local' stoa.local"
fi

info "Infra repo (stoa-infra)"
if [[ -d "$INFRA_TILT" ]]; then
  ok "stoa-infra sibling checkout at $INFRA_TILT"
else
  bad "stoa-infra not found at ../stoa-infra" \
      "git clone git@github.com:PotoMitan/stoa-infra.git ../stoa-infra"
fi

info "Env file (stateful services)"
ENVFILE="$REPO_ROOT/deploy/docker-compose/.env"
if [[ -f "$ENVFILE" ]]; then
  ok ".env present at deploy/docker-compose/.env"
else
  bad ".env missing" "cp deploy/docker-compose/.env.example deploy/docker-compose/.env and fill POSTGRES_PASSWORD + KC creds"
fi

info "k3d cluster (stoa-dev)"
if k3d cluster list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx stoa-dev; then
  ok "stoa-dev cluster exists"
else
  bad "stoa-dev cluster not created" "make dev-up (will create it)"
fi

printf "\n\033[1mResult:\033[0m %d pass, %d fail\n" "$PASS" "$FAIL"
[[ $FAIL -eq 0 ]] || exit 1
