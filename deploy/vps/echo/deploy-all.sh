#!/usr/bin/env bash
# Deploy echo server on all Arena VPS and configure gateway routes.
#
# Key lessons from live deployment:
# - All gateways run in Docker → echo must be on the same Docker network
# - STOA gateway has SSRF blocklist → can't use localhost, use container name
# - Kong DB-less → full declarative config reload (read-merge-POST /config)
# - Gravitee V4 → create API + publish plan + deploy + start (strict order)
#
# Usage: ./deploy-all.sh
set -euo pipefail

SSH_KEY=~/.ssh/id_ed25519_stoa
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VPS_KONG_STOA="51.83.45.13"   # Kong + STOA share this VPS
VPS_GRAVITEE="54.36.209.237"   # Gravitee on its own VPS

# --- Step 1: Deploy echo server on both VPS ---
for VPS in "$VPS_KONG_STOA" "$VPS_GRAVITEE"; do
  echo "=== Deploying echo server on $VPS ==="
  ssh -i "$SSH_KEY" "debian@$VPS" "mkdir -p ~/echo"
  scp -i "$SSH_KEY" "$SCRIPT_DIR/docker-compose.yml" "$SCRIPT_DIR/nginx.conf" "debian@$VPS:~/echo/"
  ssh -i "$SSH_KEY" "debian@$VPS" "cd ~/echo && docker compose up -d"
  echo "Waiting for echo server..."
  sleep 2
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://$VPS:8888/get" --connect-timeout 5)
  if [ "$HTTP_CODE" = "200" ]; then
    echo "OK: echo server on $VPS:8888"
  else
    echo "FAIL: echo server on $VPS returned HTTP $HTTP_CODE"
    exit 1
  fi
  echo ""
done

# --- Step 1b: Connect echo container to gateway Docker networks ---
echo "=== Connecting echo to gateway Docker networks ==="
# Kong VPS: stoa_default + kong_default
ssh -i "$SSH_KEY" "debian@$VPS_KONG_STOA" "
  docker network connect stoa_default echo-local 2>/dev/null || true
  docker network connect kong_default echo-local 2>/dev/null || true
  echo 'echo-local connected to stoa_default + kong_default'
"
# Gravitee VPS: gravitee_default
ssh -i "$SSH_KEY" "debian@$VPS_GRAVITEE" "
  docker network connect gravitee_default echo-local 2>/dev/null || true
  echo 'echo-local connected to gravitee_default'
"
echo ""

# --- Step 2: Register echo route on STOA gateway ---
# Uses Docker container name (echo-local) — SSRF blocklist blocks localhost
echo "=== Configuring STOA route → echo ==="
STOA_ADMIN_TOKEN="${STOA_ADMIN_API_TOKEN:?Set STOA_ADMIN_API_TOKEN from Infisical prod/gateway/arena/ADMIN_API_TOKEN}"
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://$VPS_KONG_STOA:8080/admin/apis" \
  -H "Authorization: Bearer $STOA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "arena-echo-001",
    "name": "echo-arena",
    "tenant_id": "arena",
    "path_prefix": "/echo",
    "backend_url": "http://echo-local:8888",
    "methods": ["GET", "POST"],
    "spec_hash": "arena-echo-v1",
    "activated": true
  }')
echo "STOA route: HTTP $HTTP_CODE"

# Verify
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://$VPS_KONG_STOA:8080/echo/get")
echo "STOA proxy echo: HTTP $HTTP_CODE"
echo ""

# --- Step 3: Register echo route on Kong (DB-less: read-merge-reload) ---
# Uses Docker container name (echo-local) — Kong container can't reach host localhost
echo "=== Configuring Kong route → echo ==="
KONG_CONFIG='{"_format_version":"3.0","services":[{"name":"httpbin","url":"https://httpbin.org","routes":[{"name":"httpbin-route","paths":["/httpbin"],"strip_path":true}]},{"name":"echo-local","url":"http://echo-local:8888","routes":[{"name":"echo-route","paths":["/echo"],"strip_path":true}],"tags":["stoa-arena"]}]}'

HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://$VPS_KONG_STOA:8001/config" \
  -H "Content-Type: application/json" \
  -d "$KONG_CONFIG")
echo "Kong config reload: HTTP $HTTP_CODE"

# Verify
sleep 1
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://$VPS_KONG_STOA:8000/echo/get")
echo "Kong proxy echo: HTTP $HTTP_CODE"
echo ""

# --- Step 4: Register echo API on Gravitee ---
# Uses Docker container name (echo-local) — Gravitee container can't reach host localhost
# Gravitee V4 lifecycle: create → plan (publish) → deploy → start
echo "=== Configuring Gravitee route → echo ==="
GRAVITEE_AUTH="Basic YWRtaW46YWRtaW4="
GRAVITEE_MGMT="http://$VPS_GRAVITEE:8083/management/v2/environments/DEFAULT"

# Check if echo API already exists
EXISTING=$(curl -s "${GRAVITEE_MGMT}/apis?q=echo-arena" -H "Authorization: $GRAVITEE_AUTH" | python3 -c "
import sys,json
d=json.load(sys.stdin)
apis = [a for a in d.get('data',[]) if 'echo' in a.get('name','')]
print(apis[0]['id'] if apis else '')
" 2>/dev/null || echo "")

if [ -n "$EXISTING" ]; then
  echo "Gravitee echo API already exists: $EXISTING"
else
  # Create V4 proxy API
  API_RESPONSE=$(curl -s -X POST "${GRAVITEE_MGMT}/apis" \
    -H "Authorization: $GRAVITEE_AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "echo-arena",
      "apiVersion": "1.0",
      "description": "Local echo server for Arena benchmarks",
      "definitionVersion": "V4",
      "type": "PROXY",
      "listeners": [
        {
          "type": "HTTP",
          "paths": [{"path": "/echo"}],
          "entrypoints": [{"type": "http-proxy"}]
        }
      ],
      "endpointGroups": [
        {
          "name": "default",
          "type": "http-proxy",
          "endpoints": [
            {
              "name": "echo-backend",
              "type": "http-proxy",
              "configuration": {"target": "http://echo-local:8888"}
            }
          ]
        }
      ]
    }')
  EXISTING=$(echo "$API_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','FAILED'))")
  echo "Gravitee API created: $EXISTING"

  # Create KEY_LESS plan (status=STAGING by default in Gravitee 4.6)
  PLAN_ID=$(curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/plans" \
    -H "Authorization: $GRAVITEE_AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "keyless",
      "description": "Open access for Arena",
      "definitionVersion": "V4",
      "mode": "STANDARD",
      "security": {"type": "KEY_LESS"},
      "characteristics": [],
      "status": "PUBLISHED"
    }' | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','FAILED'))" 2>/dev/null)
  echo "Gravitee plan created: $PLAN_ID"

  # Publish plan (Gravitee 4.6 creates in STAGING even with status=PUBLISHED)
  curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/plans/${PLAN_ID}/_publish" \
    -H "Authorization: $GRAVITEE_AUTH" > /dev/null 2>&1
  echo "Plan published"

  # Deploy (requires published plan)
  curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/deployments" \
    -H "Authorization: $GRAVITEE_AUTH" \
    -H "Content-Type: application/json" \
    -d '{"deploymentLabel":"arena-echo"}' > /dev/null 2>&1

  # Start
  curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/_start" \
    -H "Authorization: $GRAVITEE_AUTH" > /dev/null 2>&1 || true
  echo "Gravitee API deployed + started"
fi

sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://$VPS_GRAVITEE:8082/echo/get")
echo "Gravitee proxy echo: HTTP $HTTP_CODE"
echo ""

# --- Summary ---
echo "=== All routes configured ==="
echo "Echo direct (Kong VPS):     curl http://$VPS_KONG_STOA:8888/get"
echo "Echo direct (Gravitee VPS): curl http://$VPS_GRAVITEE:8888/get"
echo "STOA proxy:                 curl http://$VPS_KONG_STOA:8080/echo/get"
echo "Kong proxy:                 curl http://$VPS_KONG_STOA:8000/echo/get"
echo "Gravitee proxy:             curl http://$VPS_GRAVITEE:8082/echo/get"
