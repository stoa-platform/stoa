#!/usr/bin/env bash
# Live proof: a published contract with jwt_validation (inboundAuth=jwt)
# is 401 without a token, 200 with a Keycloak client_credentials token
# whose aud contains stoa-gateway, and 401 again once that token is
# expired, the issuer does not match, or the caller has no audience mapper.
#
# A second contract with no inbound auth is rejected (400) and stays unpublished.
# There is no allowUnauthenticatedREST flag.
# POST /admin/contracts with X-Forwarded-For is 404.
#
# Usage: deploy/standalone/jwt-proof.sh [image]
# Does not print the admin token or the Keycloak client secret.
set -euo pipefail

IMAGE="${1:-stoa-gateway:0.9.25}"
# Set STOA_PROOF_BIN to a gateway binary to run it on the host. Keycloak and
# nginx still run in Docker. Leave it unset to `docker run` the image.
PROOF_BIN="${STOA_PROOF_BIN:-}"
NET=stoa-jwt-proof
ADMIN_TOKEN="$(openssl rand -hex 32)"
CLIENT_SECRET="$(openssl rand -hex 24)"
NOAUD_SECRET="$(openssl rand -hex 24)"
KC_IMAGE=quay.io/keycloak/keycloak:26.4.2

cleanup() {
  if [[ -n "${GW_PID:-}" ]]; then
    kill "$GW_PID" >/dev/null 2>&1 || true
    wait "$GW_PID" >/dev/null 2>&1 || true
  fi
  sudo docker rm -f stoa-jwt-gw stoa-jwt-kc stoa-jwt-echo >/dev/null 2>&1 || true
  sudo docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sudo docker network create "$NET" >/dev/null
if [[ -n "$PROOF_BIN" ]]; then
  sudo docker run -d --name stoa-jwt-echo -p 18082:80 nginx:1.27-alpine >/dev/null
  sudo docker run -d --name stoa-jwt-kc -p 18081:8080 \
    -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
    -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
    -e KC_HOSTNAME=http://127.0.0.1:18081 \
    -e KC_HOSTNAME_STRICT=false \
    -e KC_HTTP_ENABLED=true \
    "$KC_IMAGE" start-dev >/dev/null
  KC_URL=http://127.0.0.1:18081
  BACKEND_URL=http://127.0.0.1:18082
  export KC_URL BACKEND_URL
else
  sudo docker run -d --name stoa-jwt-echo --network "$NET" nginx:1.27-alpine >/dev/null
  sudo docker run -d --name stoa-jwt-kc --network "$NET" --network-alias keycloak \
    -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
    -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
    -e KC_HOSTNAME=http://keycloak:8080 \
    -e KC_HOSTNAME_STRICT=false \
    -e KC_HTTP_ENABLED=true \
    "$KC_IMAGE" start-dev >/dev/null
  KC_URL=http://keycloak:8080
  BACKEND_URL=http://stoa-jwt-echo:80
  export KC_URL BACKEND_URL
fi

echo "waiting for keycloak"
ready=0
for _ in $(seq 1 90); do
  if sudo docker exec stoa-jwt-kc bash -lc 'exec 3<>/dev/tcp/127.0.0.1/8080 && printf "GET /realms/master HTTP/1.0\r\nHost: keycloak\r\n\r\n" >&3 && head -1 <&3' 2>/dev/null | grep -q HTTP; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" != 1 ]]; then
  echo "keycloak did not become ready" >&2
  sudo docker logs stoa-jwt-kc 2>&1 | tail -40 >&2
  exit 1
fi

sudo docker exec stoa-jwt-kc /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://127.0.0.1:8080 --realm master --user admin --password admin >/dev/null
sudo docker exec stoa-jwt-kc /opt/keycloak/bin/kcadm.sh create realms \
  -s realm=stoa -s enabled=true -s accessTokenLifespan=1 >/dev/null
sudo docker exec stoa-jwt-kc /opt/keycloak/bin/kcadm.sh create clients -r stoa \
  -s clientId=stoa-caller \
  -s secret="$CLIENT_SECRET" \
  -s serviceAccountsEnabled=true \
  -s publicClient=false \
  -s standardFlowEnabled=false \
  -s directAccessGrantsEnabled=false \
  -s protocol=openid-connect >/dev/null
sudo docker exec stoa-jwt-kc /opt/keycloak/bin/kcadm.sh create clients -r stoa \
  -s clientId=stoa-no-audience \
  -s secret="$NOAUD_SECRET" \
  -s serviceAccountsEnabled=true \
  -s publicClient=false \
  -s standardFlowEnabled=false \
  -s directAccessGrantsEnabled=false \
  -s protocol=openid-connect >/dev/null
sudo docker exec stoa-jwt-kc /opt/keycloak/bin/kcadm.sh get clients -r stoa -q clientId=stoa-caller >/tmp/stoa-jwt-caller.json
CALLER_ID="$(python3 -c 'import json; print(json.load(open("/tmp/stoa-jwt-caller.json"))[0]["id"])')"
python3 -c 'import json; json.dump({"name":"stoa-gateway-audience","protocol":"openid-connect","protocolMapper":"oidc-audience-mapper","consentRequired":False,"config":{"included.custom.audience":"stoa-gateway","id.token.claim":"false","access.token.claim":"true"}}, open("/tmp/stoa-jwt-mapper.json","w"))'
sudo docker cp /tmp/stoa-jwt-mapper.json stoa-jwt-kc:/tmp/stoa-jwt-mapper.json
sudo docker exec stoa-jwt-kc /opt/keycloak/bin/kcadm.sh create "clients/${CALLER_ID}/protocol-mappers/models" -r stoa -f /tmp/stoa-jwt-mapper.json >/dev/null

if [[ -n "$PROOF_BIN" ]]; then
  STOA_HOST=0.0.0.0 \
  STOA_PORT=18080 \
  STOA_ADMIN_API_TOKEN="$ADMIN_TOKEN" \
  STOA_AUTO_REGISTER=false \
  STOA_ROUTE_RELOAD_ENABLED=false \
  STOA_BUDGET_ENFORCEMENT_ENABLED=false \
  STOA_KAFKA_ENABLED=false \
  STOA_OTEL_ENABLED=false \
  STOA_KEYCLOAK_URL="$KC_URL" \
  STOA_KEYCLOAK_REALM=stoa \
  STOA_JWT_AUDIENCE=stoa-gateway \
  RUST_LOG=info \
  "$PROOF_BIN" >/tmp/stoa-jwt-gw.log 2>&1 &
  GW_PID=$!
else
  sudo docker run -d --name stoa-jwt-gw --network "$NET" \
    -p 18080:8080 \
    -e STOA_HOST=0.0.0.0 \
    -e STOA_PORT=8080 \
    -e STOA_ADMIN_API_TOKEN="$ADMIN_TOKEN" \
    -e STOA_AUTO_REGISTER=false \
    -e STOA_ROUTE_RELOAD_ENABLED=false \
    -e STOA_BUDGET_ENFORCEMENT_ENABLED=false \
    -e STOA_KAFKA_ENABLED=false \
    -e STOA_OTEL_ENABLED=false \
    -e STOA_KEYCLOAK_URL="$KC_URL" \
    -e STOA_KEYCLOAK_REALM=stoa \
    -e STOA_JWT_AUDIENCE=stoa-gateway \
    -e RUST_LOG=info \
    "$IMAGE" >/dev/null
fi

echo "waiting for gateway /health"
ready=0
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:18080/health >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo "gateway did not become healthy" >&2
  if [[ -n "$PROOF_BIN" ]]; then tail -60 /tmp/stoa-jwt-gw.log >&2; else sudo docker logs stoa-jwt-gw 2>&1 | tail -60 >&2; fi
  exit 1
fi

health="$(curl -sS -o /tmp/stoa-jwt-health -w '%{http_code}' http://127.0.0.1:18080/health)"
echo "GET /health $health"

admin_anon="$(curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:18080/admin/contracts -H 'content-type: application/json' -d '{}')"
echo "POST /admin/contracts without token $admin_anon"

admin_fwd="$(curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:18080/admin/contracts \
  -H "authorization: Bearer $ADMIN_TOKEN" \
  -H 'content-type: application/json' \
  -H 'X-Forwarded-For: 203.0.113.10' \
  -H 'X-Forwarded-Host: api.gostoa.dev' \
  -d '{}')"
echo "POST /admin/contracts via forwarded headers $admin_fwd"

protected="$(python3 -c 'import json,os; print(json.dumps({"name":"live-api","version":"1.0.0","tenant_id":"demo","status":"published","classification":"H","inboundAuth":"jwt","endpoints":[{"path":"/ping","methods":["GET"],"backend_url":os.environ["BACKEND_URL"]}]}))')"
open="$(python3 -c 'import json,os; print(json.dumps({"name":"open-api","version":"1.0.0","tenant_id":"demo","status":"published","classification":"H","endpoints":[{"path":"/ping","methods":["GET"],"backend_url":os.environ["BACKEND_URL"]}]}))')"

protected_status="$(curl -sS -o /tmp/stoa-jwt-contract -w '%{http_code}' -X POST http://127.0.0.1:18080/admin/contracts \
  -H "authorization: Bearer $ADMIN_TOKEN" -H 'content-type: application/json' -d "$protected")"
echo "POST protected contract $protected_status $(cat /tmp/stoa-jwt-contract)"

open_status="$(curl -sS -o /tmp/stoa-jwt-open -w '%{http_code}' -X POST http://127.0.0.1:18080/admin/contracts \
  -H "authorization: Bearer $ADMIN_TOKEN" -H 'content-type: application/json' -d "$open")"
echo "POST open contract $open_status $(cat /tmp/stoa-jwt-open)"

anon="$(curl -sS -D /tmp/stoa-jwt-anon-hdr -o /tmp/stoa-jwt-anon -w '%{http_code}' http://127.0.0.1:18080/apis/demo/live-api/ping)"
echo "GET protected without token $anon $(cat /tmp/stoa-jwt-anon)"
grep -i '^www-authenticate:' /tmp/stoa-jwt-anon-hdr

open_anon="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/apis/demo/open-api/ping)"
echo "GET open contract without token $open_anon"

if [[ -n "$PROOF_BIN" ]]; then
  token_json="$(curl -sS --max-time 20 -X POST "$KC_URL/realms/stoa/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    -d "grant_type=client_credentials" -d "client_id=stoa-caller" -d "client_secret=$CLIENT_SECRET")"
else
  token_json="$(sudo docker exec stoa-jwt-gw curl -sS --max-time 20 -X POST "$KC_URL/realms/stoa/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    -d "grant_type=client_credentials" -d "client_id=stoa-caller" -d "client_secret=$CLIENT_SECRET")"
fi
ACCESS_TOKEN="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["access_token"])' "$token_json")"
ISS="$(python3 -c 'import base64,json,sys; p=sys.argv[1].split(".")[1]; p+="="*((4-len(p)%4)%4); print(json.loads(base64.urlsafe_b64decode(p))["iss"])' "$ACCESS_TOKEN")"
python3 -c 'import base64,json,sys; p=sys.argv[1].split(".")[1]; p+="="*((4-len(p)%4)%4); aud=json.loads(base64.urlsafe_b64decode(p)).get("aud"); aud=[aud] if isinstance(aud,str) else list(aud or []);
assert "stoa-gateway" in aud, aud; print("token aud", ",".join(aud))' "$ACCESS_TOKEN"
echo "token iss=$ISS"

authed="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/apis/demo/live-api/ping -H "authorization: Bearer $ACCESS_TOKEN")"
echo "GET protected with token $authed"

if [[ -n "$PROOF_BIN" ]]; then
  noaud_json="$(curl -sS --max-time 20 -X POST "$KC_URL/realms/stoa/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    -d "grant_type=client_credentials" -d "client_id=stoa-no-audience" -d "client_secret=$NOAUD_SECRET")"
else
  noaud_json="$(sudo docker exec stoa-jwt-gw curl -sS --max-time 20 -X POST "$KC_URL/realms/stoa/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    -d "grant_type=client_credentials" -d "client_id=stoa-no-audience" -d "client_secret=$NOAUD_SECRET")"
fi
NOAUD_TOKEN="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["access_token"])' "$noaud_json")"
python3 -c 'import base64,json,sys; p=sys.argv[1].split(".")[1]; p+="="*((4-len(p)%4)%4); aud=json.loads(base64.urlsafe_b64decode(p)).get("aud"); aud=[aud] if isinstance(aud,str) else list(aud or []);
assert "stoa-gateway" not in aud, aud' "$NOAUD_TOKEN"
noaud="$(curl -sS -o /tmp/stoa-jwt-noaud -w '%{http_code}' http://127.0.0.1:18080/apis/demo/live-api/ping -H "authorization: Bearer $NOAUD_TOKEN")"
echo "GET protected with token missing audience $noaud $(cat /tmp/stoa-jwt-noaud)"

# Realm accessTokenLifespan is 1s. Validator leeway is 30s.
echo "waiting for the access token to age past the 30s leeway"
sleep 35
expired="$(curl -sS -o /tmp/stoa-jwt-exp -w '%{http_code}' http://127.0.0.1:18080/apis/demo/live-api/ping -H "authorization: Bearer $ACCESS_TOKEN")"
echo "GET protected with expired token $expired $(cat /tmp/stoa-jwt-exp)"

# Signed by a different key, iss is not the realm. Fail closed.
WRONG_ISS='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Im5vdC1vdXIta2V5In0.eyJzdWIiOiJldmlsIiwiaXNzIjoiaHR0cDovL2V2aWwuZXhhbXBsZS9yZWFsbXMvc3RvYSIsImV4cCI6NDA3MDkwODgwMCwiaWF0IjoxNzAwMDAwMDAwfQ.not-a-valid-signature'
wrong="$(curl -sS -o /tmp/stoa-jwt-wrong -w '%{http_code}' http://127.0.0.1:18080/apis/demo/live-api/ping -H "authorization: Bearer $WRONG_ISS")"
echo "GET protected with wrong issuer $wrong $(cat /tmp/stoa-jwt-wrong)"

test "$health" = 200
test "$admin_anon" = 401
test "$admin_fwd" = 404
test "$protected_status" = 201
test "$open_status" = 400
grep -q 'no inbound auth' /tmp/stoa-jwt-open
test "$anon" = 401
test "$open_anon" = 404
test "$authed" = 200
test "$noaud" = 401
grep -q 'Invalid token audience' /tmp/stoa-jwt-noaud
test "$expired" = 401
test "$wrong" = 401
test "$ISS" = "$KC_URL/realms/stoa"
echo PROOF_OK
