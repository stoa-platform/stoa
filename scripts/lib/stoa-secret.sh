#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 STOA Platform
#
# stoa-secret.sh — read a tooling secret from OpenBao (ADR-075, replaces Infisical).
#
#   source scripts/lib/stoa-secret.sh
#   KEY=$(stoa_secret anthropic ANTHROPIC_API_KEY) || KEY=""
#   scripts/lib/stoa-secret.sh anthropic ANTHROPIC_API_KEY   # same, as a command
#
# Prints field <field> of the KV v2 secret secret/stoa/tooling/<path> on stdout,
# without a trailing newline. On failure it prints one line on stderr and returns
# 1 (2 for a usage error). The token is never printed and reaches curl only as a
# header read from stdin. It is renewed (renew-self) at most once a day per
# address, recorded under ~/.cache/stoa; a failed renewal is ignored.
#
#   STOA_OPENBAO_ADDR              default https://127.0.0.1:18200 (SSH tunnel)
#   STOA_OPENBAO_CACERT            default ~/.config/stoa/openbao-ca.pem
#   STOA_OPENBAO_TOKEN             if unset: macOS Keychain item (service
#   STOA_OPENBAO_KEYCHAIN_SERVICE  default stoa-openbao, account "tooling"),
#                                  then ~/.config/stoa/openbao-tooling-token

_stoa_secret_err() {
  printf 'stoa_secret: %s\n' "$1" >&2
}

# Print the token (env, then Keychain, then file) for capture by the caller.
_stoa_secret_token() {
  local token="${STOA_OPENBAO_TOKEN:-}" service file
  service=${STOA_OPENBAO_KEYCHAIN_SERVICE:-stoa-openbao}
  if [ -z "$token" ] && command -v security >/dev/null 2>&1; then
    token=$(command security find-generic-password -s "$service" -a tooling -w 2>/dev/null) || token=""
  fi
  file="${HOME:-}/.config/stoa/openbao-tooling-token"
  if [ -z "$token" ] && [ -n "${HOME:-}" ] && [ -r "$file" ]; then
    token=$(cat "$file" 2>/dev/null) || token=""
  fi
  printf '%s' "${token//[[:space:]]/}"
}

# _stoa_secret_curl <cacert> <url> [curl options...]
# Reads the "X-Vault-Token: ..." header on stdin; prints the body, a newline
# and the HTTP status. -q ignores ~/.curlrc; no proxy, HTTPS only.
_stoa_secret_curl() {
  local cacert=$1 url=$2
  shift 2
  command curl -q -s --noproxy '*' --proto '=https' --connect-timeout 5 --max-time 20 \
    --cacert "$cacert" -H @- -w '\n%{http_code}' "$@" "$url"
}

# True at most once a day per address; records the attempt in ~/.cache/stoa.
_stoa_secret_renew_due() {
  local dir="${HOME:-}/.cache/stoa" stamp now last=0
  [ -n "${HOME:-}" ] || return 1
  stamp="$dir/openbao-renew-${1//[^A-Za-z0-9]/_}"
  now=$(date +%s) || return 1
  [ -r "$stamp" ] && IFS= read -r last < "$stamp"
  case $last in '' | *[!0-9]*) last=0 ;; esac
  [ $((now - last)) -ge 86400 ] || return 1
  mkdir -p "$dir" 2>/dev/null && printf '%s\n' "$now" >| "$stamp" 2>/dev/null
}

# stoa_secret <path-under-stoa/tooling> <field>
# Runs in a subshell: no variable leaks, and xtrace stays off whatever the caller set.
stoa_secret() (
  set +x +e +u
  set +o pipefail
  local name=${1:-} field=${2:-} addr cacert token resp rc code value why
  local re='^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$'
  if [ "$#" -ne 2 ] || [ -z "$field" ]; then
    _stoa_secret_err "usage: stoa_secret <path-under-stoa/tooling> <field>"
    return 2
  fi
  if ! [[ $name =~ $re ]]; then
    _stoa_secret_err "invalid path '$name' (expected a path under stoa/tooling, e.g. anthropic)"
    return 2
  fi
  command -v curl >/dev/null 2>&1 || { _stoa_secret_err "curl not found"; return 1; }
  command -v jq >/dev/null 2>&1 || { _stoa_secret_err "jq not found"; return 1; }
  addr=${STOA_OPENBAO_ADDR:-https://127.0.0.1:18200}
  addr=${addr%/}
  cacert=${STOA_OPENBAO_CACERT:-${HOME:-}/.config/stoa/openbao-ca.pem}
  if [ ! -r "$cacert" ]; then
    _stoa_secret_err "CA file not readable: $cacert (set STOA_OPENBAO_CACERT)"
    return 1
  fi
  token=$(_stoa_secret_token)
  if [ -z "$token" ]; then
    _stoa_secret_err "no OpenBao token (set STOA_OPENBAO_TOKEN, add the Keychain item or the token file)"
    return 1
  fi

  resp=$(printf 'X-Vault-Token: %s\n' "$token" |
    _stoa_secret_curl "$cacert" "$addr/v1/secret/data/stoa/tooling/$name")
  rc=$?
  if [ "$rc" -ne 0 ]; then
    case $rc in
      7) why="connection refused, is the tunnel up?" ;;
      28) why="timed out" ;;
      35 | 51 | 58 | 60 | 77 | 83 | 90 | 91) why="TLS verification failed, check STOA_OPENBAO_CACERT" ;;
      *) why="curl exit $rc" ;;
    esac
    _stoa_secret_err "OpenBao unreachable at $addr ($why)"
    return 1
  fi
  code=${resp##*$'\n'}
  resp=${resp%$'\n'*}
  case $code in
    200) ;;
    403) _stoa_secret_err "permission denied on stoa/tooling/$name (HTTP 403: token invalid, expired or not allowed)"; return 1 ;;
    404) _stoa_secret_err "secret stoa/tooling/$name not found (HTTP 404)"; return 1 ;;
    503) _stoa_secret_err "OpenBao sealed or unavailable at $addr (HTTP 503)"; return 1 ;;
    *) _stoa_secret_err "unexpected HTTP $code from OpenBao for stoa/tooling/$name"; return 1 ;;
  esac
  value=$(printf '%s' "$resp" | command jq -r --arg f "$field" \
    '.data.data[$f] // empty | if type == "string" then . else tojson end' 2>/dev/null)
  if [ -z "$value" ]; then
    _stoa_secret_err "field $field not found in stoa/tooling/$name"
    return 1
  fi

  if _stoa_secret_renew_due "$addr"; then
    printf 'X-Vault-Token: %s\n' "$token" |
      _stoa_secret_curl "$cacert" "$addr/v1/auth/token/renew-self" -o /dev/null \
        -H 'Content-Type: application/json' -d '{}' >/dev/null 2>&1
  fi
  printf '%s' "$value"
)

if [ -n "${BASH_VERSION:-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
  stoa_secret "$@"
  exit $?
fi
