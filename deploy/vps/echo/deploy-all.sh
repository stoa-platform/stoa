#!/usr/bin/env bash
# Deploy echo server on all Arena VPS and configure gateway routes.
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

# --- Step 2: Register echo route on STOA gateway ---
echo "=== Configuring STOA route → echo ==="
STOA_ADMIN_TOKEN="arena-admin-token-2026"
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://$VPS_KONG_STOA:8080/admin/apis" \
  -H "Authorization: Bearer $STOA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "arena-echo-001",
    "name": "echo-arena",
    "tenant_id": "arena",
    "path_prefix": "/echo",
    "backend_url": "http://localhost:8888",
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
echo "=== Configuring Kong route → echo ==="
# Get current config
CURRENT_CONFIG=$(curl -s "http://$VPS_KONG_STOA:8001/services" 2>/dev/null)
CURRENT_PLUGINS=$(curl -s "http://$VPS_KONG_STOA:8001/plugins" 2>/dev/null)
CURRENT_CONSUMERS=$(curl -s "http://$VPS_KONG_STOA:8001/consumers" 2>/dev/null)

# Build declarative config with echo service added
python3 - "$CURRENT_CONFIG" "$CURRENT_PLUGINS" "$CURRENT_CONSUMERS" <<'PYEOF'
import json, sys

services_resp = json.loads(sys.argv[1])
plugins_resp = json.loads(sys.argv[2])
consumers_resp = json.loads(sys.argv[3])

services = []
for svc in services_resp.get("data", []):
    port = svc.get("port", 80)
    path = svc.get("path") or ""
    url = f"{svc['protocol']}://{svc['host']}:{port}{path}"
    routes = []
    for r in svc.get("routes", []):
        routes.append({"name": r["name"], "paths": r.get("paths", []), "strip_path": r.get("strip_path", True)})
    entry = {"name": svc["name"], "url": url, "routes": routes}
    if svc.get("tags"):
        entry["tags"] = svc["tags"]
    services.append(entry)

# Add echo service if not present
echo_names = [s["name"] for s in services if "echo" in s["name"]]
if not echo_names:
    services.append({
        "name": "echo-local",
        "url": "http://localhost:8888",
        "routes": [{"name": "echo-route", "paths": ["/echo"], "strip_path": True}],
        "tags": ["stoa-arena"]
    })

plugins = []
for p in plugins_resp.get("data", []):
    entry = {"name": p["name"], "config": p.get("config", {})}
    if p.get("service"):
        # Find service name by ID
        for svc in services_resp.get("data", []):
            if svc["id"] == p["service"]["id"]:
                entry["service"] = svc["name"]
                break
    if p.get("consumer"):
        for c in consumers_resp.get("data", []):
            if c["id"] == p["consumer"]["id"]:
                entry["consumer"] = c["username"]
                break
    if p.get("tags"):
        entry["tags"] = p["tags"]
    plugins.append(entry)

consumers = []
for c in consumers_resp.get("data", []):
    entry = {"username": c["username"]}
    if c.get("tags"):
        entry["tags"] = c["tags"]
    consumers.append(entry)

config = {"_format_version": "3.0", "services": services, "plugins": plugins, "consumers": consumers}
print(json.dumps(config))
PYEOF

KONG_CONFIG=$(python3 - "$CURRENT_CONFIG" "$CURRENT_PLUGINS" "$CURRENT_CONSUMERS" <<'PYEOF'
import json, sys
services_resp = json.loads(sys.argv[1])
plugins_resp = json.loads(sys.argv[2])
consumers_resp = json.loads(sys.argv[3])
services = []
for svc in services_resp.get("data", []):
    port = svc.get("port", 80)
    path = svc.get("path") or ""
    url = f"{svc['protocol']}://{svc['host']}:{port}{path}"
    routes = []
    for r in svc.get("routes", []):
        routes.append({"name": r["name"], "paths": r.get("paths", []), "strip_path": r.get("strip_path", True)})
    entry = {"name": svc["name"], "url": url, "routes": routes}
    if svc.get("tags"):
        entry["tags"] = svc["tags"]
    services.append(entry)
echo_names = [s["name"] for s in services if "echo" in s["name"]]
if not echo_names:
    services.append({"name": "echo-local", "url": "http://localhost:8888", "routes": [{"name": "echo-route", "paths": ["/echo"], "strip_path": True}], "tags": ["stoa-arena"]})
plugins = []
for p in plugins_resp.get("data", []):
    entry = {"name": p["name"], "config": p.get("config", {})}
    if p.get("service"):
        for svc in services_resp.get("data", []):
            if svc["id"] == p["service"]["id"]:
                entry["service"] = svc["name"]
                break
    if p.get("tags"):
        entry["tags"] = p["tags"]
    plugins.append(entry)
consumers = []
for c in consumers_resp.get("data", []):
    entry = {"username": c["username"]}
    if c.get("tags"):
        entry["tags"] = c["tags"]
    consumers.append(entry)
config = {"_format_version": "3.0", "services": services, "plugins": plugins, "consumers": consumers}
print(json.dumps(config))
PYEOF
)

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
echo "=== Configuring Gravitee route → echo ==="
GRAVITEE_AUTH="Basic YWRtaW46YWRtaW4="
GRAVITEE_MGMT="http://$VPS_GRAVITEE:8083/management/v2/environments/DEFAULT"

# Check if echo API already exists
EXISTING=$(curl -s "${GRAVITEE_MGMT}/apis?q=echo-local" -H "Authorization: $GRAVITEE_AUTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',[{}])[0].get('id','') if d.get('data') else '')" 2>/dev/null || echo "")

if [ -n "$EXISTING" ]; then
  echo "Gravitee echo API already exists: $EXISTING"
else
  # Create V4 proxy API
  API_RESPONSE=$(curl -s -X POST "${GRAVITEE_MGMT}/apis" \
    -H "Authorization: $GRAVITEE_AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "echo-local",
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
              "configuration": {"target": "http://localhost:8888"}
            }
          ]
        }
      ]
    }')
  EXISTING=$(echo "$API_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','FAILED'))")
  echo "Gravitee API created: $EXISTING"

  # Start + Deploy
  curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/_start" -H "Authorization: $GRAVITEE_AUTH" > /dev/null 2>&1 || true
  curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/deployments" -H "Authorization: $GRAVITEE_AUTH" -H "Content-Type: application/json" -d '{"deploymentLabel":"arena"}' > /dev/null 2>&1
  echo "Gravitee API started + deployed"

  # Create KEY_LESS plan
  curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/plans" \
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
    }' > /dev/null 2>&1
  echo "Gravitee KEY_LESS plan created"

  # Redeploy
  curl -s -X POST "${GRAVITEE_MGMT}/apis/${EXISTING}/deployments" -H "Authorization: $GRAVITEE_AUTH" -H "Content-Type: application/json" -d '{"deploymentLabel":"arena-plan"}' > /dev/null 2>&1
fi

sleep 2
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
