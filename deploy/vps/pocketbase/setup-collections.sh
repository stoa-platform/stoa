#!/usr/bin/env bash
# Create PocketBase collections matching HEGEMON state.db schema
# Compatible with PocketBase v0.23+ (superuser auth, fields API)
#
# Usage: ./setup-collections.sh [PB_URL]
set -euo pipefail

PB_URL="${1:-http://localhost:8090}"
ADMIN_EMAIL="${PB_ADMIN_EMAIL:-admin@gostoa.dev}"
ADMIN_PASSWORD="${PB_ADMIN_PASSWORD:?Set PB_ADMIN_PASSWORD}"

echo "=== PocketBase Collection Setup ==="
echo "Target: ${PB_URL}"
echo ""

# Step 1: Create superuser (PB v0.23+ uses _superusers collection)
echo "[1/5] Bootstrapping superuser account..."
BOOTSTRAP=$(curl -sf -X POST "${PB_URL}/api/collections/_superusers/records" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\",\"passwordConfirm\":\"${ADMIN_PASSWORD}\"}" 2>&1) || true

if echo "$BOOTSTRAP" | grep -q '"id"'; then
  echo "  Superuser created: ${ADMIN_EMAIL}"
else
  echo "  Superuser already exists (or error) — continuing with auth"
fi

# Step 2: Authenticate (PB v0.23+ endpoint)
echo "[2/5] Authenticating..."
AUTH_RESPONSE=$(curl -sf -X POST "${PB_URL}/api/collections/_superusers/auth-with-password" \
  -H "Content-Type: application/json" \
  -d "{\"identity\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}")

TOKEN=$(echo "$AUTH_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "  Token obtained."

# Step 3: Create "sessions" collection
echo "[3/5] Creating 'sessions' collection..."
curl -sf -X POST "${PB_URL}/api/collections" \
  -H "Content-Type: application/json" \
  -H "Authorization: ${TOKEN}" \
  -d '{
    "name": "sessions",
    "type": "base",
    "fields": [
      {"name": "instance_id", "type": "text", "required": true},
      {"name": "project",     "type": "text", "required": true},
      {"name": "role",        "type": "text", "required": false},
      {"name": "ticket",      "type": "text", "required": false},
      {"name": "branch",      "type": "text", "required": false},
      {"name": "step",        "type": "text", "required": true},
      {"name": "pr",          "type": "number", "required": false},
      {"name": "host",        "type": "text", "required": false},
      {"name": "source",      "type": "text", "required": false},
      {"name": "pid",         "type": "number", "required": false},
      {"name": "started_at",  "type": "text", "required": false},
      {"name": "updated_at",  "type": "text", "required": false}
    ],
    "indexes": ["CREATE UNIQUE INDEX idx_session_instance ON sessions (instance_id)"],
    "listRule": "",
    "viewRule": "",
    "createRule": "",
    "updateRule": "",
    "deleteRule": ""
  }' > /dev/null && echo "  sessions: OK" || echo "  sessions: already exists or error"

# Step 4: Create "milestones" collection
echo "[4/5] Creating 'milestones' collection..."
curl -sf -X POST "${PB_URL}/api/collections" \
  -H "Content-Type: application/json" \
  -H "Authorization: ${TOKEN}" \
  -d '{
    "name": "milestones",
    "type": "base",
    "fields": [
      {"name": "ticket",      "type": "text", "required": true},
      {"name": "step",        "type": "text", "required": true},
      {"name": "instance_id", "type": "text", "required": true},
      {"name": "project",     "type": "text", "required": true},
      {"name": "pr",          "type": "number", "required": false},
      {"name": "sha",         "type": "text", "required": false},
      {"name": "detail",      "type": "text", "required": false},
      {"name": "event_at",    "type": "text", "required": false}
    ],
    "indexes": [
      "CREATE INDEX idx_milestone_ticket ON milestones (ticket)"
    ],
    "listRule": "",
    "viewRule": "",
    "createRule": "",
    "updateRule": null,
    "deleteRule": null
  }' > /dev/null && echo "  milestones: OK" || echo "  milestones: already exists or error"

# Step 5: Create "claims" collection
echo "[5/5] Creating 'claims' collection..."
curl -sf -X POST "${PB_URL}/api/collections" \
  -H "Content-Type: application/json" \
  -H "Authorization: ${TOKEN}" \
  -d '{
    "name": "claims",
    "type": "base",
    "fields": [
      {"name": "claim_id",     "type": "text", "required": true},
      {"name": "ticket",       "type": "text", "required": true},
      {"name": "phase",        "type": "number", "required": false},
      {"name": "mega_id",      "type": "text", "required": false},
      {"name": "owner",        "type": "text", "required": false},
      {"name": "pid",          "type": "number", "required": false},
      {"name": "host",         "type": "text", "required": false},
      {"name": "branch",       "type": "text", "required": false},
      {"name": "deps",         "type": "text", "required": false},
      {"name": "claimed_at",   "type": "text", "required": false},
      {"name": "completed_at", "type": "text", "required": false}
    ],
    "indexes": [
      "CREATE UNIQUE INDEX idx_claim_id ON claims (claim_id)",
      "CREATE INDEX idx_claim_owner ON claims (owner)",
      "CREATE INDEX idx_claim_mega ON claims (mega_id)"
    ],
    "listRule": "",
    "viewRule": "",
    "createRule": "",
    "updateRule": "",
    "deleteRule": ""
  }' > /dev/null && echo "  claims: OK" || echo "  claims: already exists or error"

echo ""
echo "=== Setup Complete ==="
echo "Admin UI: ${PB_URL}/_/"
echo "API: ${PB_URL}/api/collections/{sessions,milestones,claims}/records"
