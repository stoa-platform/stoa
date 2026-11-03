#!/usr/bin/env bash
# Resolve the Health Smoke base domain for the environment that was actually
# deployed (CAB-2362). Used by .github/workflows/reusable-health-smoke.yml.
#
# Inputs (env):
#   SMOKE_ENV            deployed environment: dev | prod
#   SMOKE_INPUT_DOMAIN   optional workflow input `base-domain` (highest priority)
#   SMOKE_VAR_DOMAIN     optional repo variable SMOKE_BASE_DOMAIN_<ENV>
# Outputs (GITHUB_OUTPUT, or stdout when unset): domain=<base>, skip=true|false
#
# Precedence: input > repo variable > derived default. The only derived default
# is the public prod domain; dev has no public base domain yet, so a dev
# deploy without SMOKE_BASE_DOMAIN_DEV is skipped with a visible warning and
# is never probed against prod.
set -euo pipefail

PROD_DEFAULT_DOMAIN="gostoa.dev"

env_name="${SMOKE_ENV:-}"
input="${SMOKE_INPUT_DOMAIN:-}"
var="${SMOKE_VAR_DOMAIN:-}"
out="${GITHUB_OUTPUT:-/dev/stdout}"

case "$env_name" in
  prod) default="$PROD_DEFAULT_DOMAIN" ;;
  dev)  default="" ;;
  *) echo "::error::Unknown smoke environment '${env_name}' (expected dev or prod)"; exit 1 ;;
esac

domain="${input// /}"
[ -n "$domain" ] || domain="${var// /}"
[ -n "$domain" ] || domain="$default"

if [ -z "$domain" ]; then
  msg="Health Smoke skipped: no public smoke domain for '${env_name}'. Set repo variable SMOKE_BASE_DOMAIN_${env_name^^} to enable it."
  echo "::warning::${msg}"
  [ -z "${GITHUB_STEP_SUMMARY:-}" ] || echo "### ${msg}" >> "$GITHUB_STEP_SUMMARY"
  { echo "domain="; echo "skip=true"; } >> "$out"
  exit 0
fi

# Public DNS names only: reject IP literals, ports, paths and odd characters.
if [[ "$domain" =~ ^[0-9.]+$ || "$domain" == *:* || ! "$domain" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]]; then
  echo "::error::Smoke domain for '${env_name}' must be a public DNS name"
  exit 1
fi

# A dev deploy must never be judged on prod.
if [ "$env_name" = "dev" ] && [ "$domain" = "$PROD_DEFAULT_DOMAIN" ]; then
  echo "::error::Dev smoke resolved to the prod domain; refusing to probe prod after a dev deploy"
  exit 1
fi

echo "Smoke targets: *.${domain} (environment: ${env_name})"
{ echo "domain=${domain}"; echo "skip=false"; } >> "$out"
