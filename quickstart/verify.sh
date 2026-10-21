#!/usr/bin/env bash
# Declare one API on the gateway, then check access control:
#   no token       -> 401
#   invalid token  -> 401
#   valid token    -> 200
# Exits non-zero otherwise. Does not print the admin token or the client secret.
# The run is bounded by VERIFY_TIMEOUT seconds (default 120). GNU timeout is
# used when it exists. Otherwise a Perl supervisor puts this script in its
# own session and, at the deadline, sends TERM then KILL to that process group.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-120}"

if [[ "${VERIFY_BOUNDED:-}" != "1" ]]; then
  export VERIFY_BOUNDED=1
  if command -v timeout >/dev/null 2>&1; then
    exec timeout --signal=TERM "${VERIFY_TIMEOUT}" "$0" "$@"
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    exec gtimeout --signal=TERM "${VERIFY_TIMEOUT}" "$0" "$@"
  fi
  if command -v perl >/dev/null 2>&1; then
    # setsid so the child and every process it starts share one group.
    # At the deadline, TERM then KILL that group. A blocked docker command is not waited out.
    exec perl -e '
      use POSIX qw(setsid WNOHANG);
      use Time::HiRes qw(time sleep);
      my $limit = shift @ARGV;
      my $pid = fork();
      die "fork: $!\n" unless defined $pid;
      if ($pid == 0) {
        setsid() or die "setsid: $!\n";
        exec @ARGV or die "exec: $!\n";
      }
      my $deadline = time() + $limit;
      while (1) {
        my $reaped = waitpid($pid, WNOHANG);
        if ($reaped == $pid) {
          my $status = $?;
          exit(($status & 127) ? 128 + ($status & 127) : $status >> 8);
        }
        die "waitpid: $!\n" if $reaped == -1;
        if (time() >= $deadline) {
          print STDERR "verify: exceeded ${limit}s\n";
          kill "TERM", -$pid;
          sleep 0.2;
          kill "KILL", -$pid;
          waitpid($pid, 0);
          exit 124;
        }
        sleep 0.05;
      }
    ' -- "${VERIFY_TIMEOUT}" "$0" "$@"
  fi
  echo "verify: need timeout, gtimeout, or perl to bound the run" >&2
  exit 1
fi

cd "$(dirname "$0")"

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8081}"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
REALM=quickstart
CLIENT_ID=quickstart-caller
API_PATH="/apis/quickstart/ping-api/ping"
expired=0

fail() {
  echo "verify: $*" >&2
  exit 1
}

dump_logs() {
  docker compose logs --tail=80 gateway keycloak control-plane >&2 || true
}

on_expire() {
  expired=1
  echo "verify: exceeded ${VERIFY_TIMEOUT}s" >&2
  dump_logs
  exit 1
}

trap on_expire TERM
trap 'status=$?; if [[ "$status" != 0 && "$expired" != 1 ]]; then dump_logs; fi' EXIT

# Test hook: a foreground child that ignores TERM. Only a group KILL stops it.
if [[ "${VERIFY_BOUND_FIXTURE:-}" == "1" ]]; then
  perl -e '$SIG{TERM} = "IGNORE"; sleep 30; exit 0'
  exit 0
fi

echo "control plane $(curl -fsS --max-time 10 "$CONTROL_PLANE_URL/health" >/dev/null && echo ok || echo down)"
cp_code="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "$CONTROL_PLANE_URL/health" || true)"
[[ "$cp_code" == "200" ]] || fail "control plane /health returned $cp_code"

gw_code="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "$GATEWAY_URL/health" || true)"
echo "gateway /health $gw_code"
[[ "$gw_code" == "200" ]] || fail "gateway /health returned $gw_code"

kc_user="$(docker compose exec -T keycloak printenv KC_BOOTSTRAP_ADMIN_USERNAME)"
kc_pass="$(docker compose exec -T keycloak printenv KC_BOOTSTRAP_ADMIN_PASSWORD)"
admin_token="$(docker compose exec -T gateway printenv STOA_ADMIN_API_TOKEN)"
kc_user="${kc_user//$'\r'/}"
kc_pass="${kc_pass//$'\r'/}"
admin_token="${admin_token//$'\r'/}"
[[ -n "$kc_user" && -n "$kc_pass" && -n "$admin_token" ]] || fail "missing demo credentials in the running containers"

echo "configuring keycloak realm"
docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://127.0.0.1:8080 \
  --realm master \
  --user "$kc_user" \
  --password "$kc_pass" >/dev/null

if ! docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get "realms/$REALM" >/dev/null 2>&1; then
  docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh create realms \
    -s "realm=$REALM" -s enabled=true >/dev/null
fi

existing_id="$(
  docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients -r "$REALM" -q "clientId=$CLIENT_ID" --fields id --format csv --noquotes 2>/dev/null \
    | tr -d '\r' | awk 'NF && $0 != "id" { print; exit }' || true
)"
if [[ -n "$existing_id" ]]; then
  docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh delete "clients/$existing_id" -r "$REALM" >/dev/null
fi

client_secret="$(openssl rand -hex 24)"
docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh create clients -r "$REALM" \
  -s "clientId=$CLIENT_ID" \
  -s "secret=$client_secret" \
  -s serviceAccountsEnabled=true \
  -s publicClient=false \
  -s standardFlowEnabled=false \
  -s directAccessGrantsEnabled=false \
  -s protocol=openid-connect >/dev/null

contract='{"name":"ping-api","version":"1.0.0","tenant_id":"quickstart","status":"published","classification":"H","inboundAuth":"jwt","endpoints":[{"path":"/ping","methods":["GET"],"backend_url":"http://backend:80"}]}'

declare_code="$(
  curl -sS --max-time 20 -o /tmp/stoa-quickstart-contract.json -w '%{http_code}' \
    -X POST "$GATEWAY_URL/admin/contracts" \
    -H "authorization: Bearer $admin_token" \
    -H 'content-type: application/json' \
    -d "$contract"
)"
echo "POST /admin/contracts $declare_code"
if [[ "$declare_code" != "201" && "$declare_code" != "200" ]]; then
  cat /tmp/stoa-quickstart-contract.json >&2
  fail "contract declaration returned $declare_code"
fi

anon_code="$(curl -sS --max-time 20 -o /tmp/stoa-quickstart-anon.txt -w '%{http_code}' "$GATEWAY_URL$API_PATH" || true)"
echo "GET without token $anon_code"
if [[ "$anon_code" != "401" ]]; then
  cat /tmp/stoa-quickstart-anon.txt >&2
  fail "expected 401 without a token, got $anon_code"
fi

bad_code="$(
  curl -sS --max-time 20 -o /tmp/stoa-quickstart-bad.txt -w '%{http_code}' \
    "$GATEWAY_URL$API_PATH" \
    -H "authorization: Bearer invalid" || true
)"
echo "GET with invalid token $bad_code"
if [[ "$bad_code" != "401" ]]; then
  cat /tmp/stoa-quickstart-bad.txt >&2
  fail "expected 401 with an invalid token, got $bad_code"
fi

token_json="$(
  docker compose exec -T gateway curl -sS --max-time 20 -X POST \
    "http://keycloak:8080/realms/$REALM/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=client_credentials' \
    --data-urlencode "client_id=$CLIENT_ID" \
    --data-urlencode "client_secret=$client_secret"
)"
access_token="$(printf '%s' "$token_json" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
[[ -n "$access_token" ]] || fail "token request did not return an access token"

authed_code="$(
  curl -sS --max-time 20 -o /tmp/stoa-quickstart-authed.txt -w '%{http_code}' \
    "$GATEWAY_URL$API_PATH" \
    -H "authorization: Bearer $access_token" || true
)"
echo "GET with token $authed_code"
if [[ "$authed_code" != "200" ]]; then
  cat /tmp/stoa-quickstart-authed.txt >&2
  fail "expected 200 with a token, got $authed_code"
fi

echo "VERIFY_OK"
