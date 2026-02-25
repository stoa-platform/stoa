#!/usr/bin/env bash
# Create PocketBase collections matching HEGEMON state.db schema
# Run once after first deploy, or after schema changes.
#
# Usage: ./setup-collections.sh [PB_URL]
set -euo pipefail

PB_URL="${1:-http://localhost:8090}"
ADMIN_EMAIL="${PB_ADMIN_EMAIL:-admin@gostoa.dev}"
ADMIN_PASSWORD="${PB_ADMIN_PASSWORD:?Set PB_ADMIN_PASSWORD}"

echo "=== PocketBase Collection Setup ==="
echo "Target: ${PB_URL}"
echo ""

# Step 1: Create admin account (only works when no admins exist)
echo "[1/5] Bootstrapping admin account..."
BOOTSTRAP=$(curl -sf -X POST "${PB_URL}/api/admins" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\",\"passwordConfirm\":\"${ADMIN_PASSWORD}\"}" 2>&1) || true

if echo "$BOOTSTRAP" | grep -q '"id"'; then
  echo "  Admin created: ${ADMIN_EMAIL}"
else
  echo "  Admin already exists (or error) — continuing with auth"
fi

# Step 2: Authenticate
echo "[2/5] Authenticating..."
AUTH_RESPONSE=$(curl -sf -X POST "${PB_URL}/api/admins/auth-with-password" \
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
    "schema": [
      {"name": "instance_id", "type": "text", "required": true, "options": {"min": 1, "max": 50}},
      {"name": "project",     "type": "text", "required": true, "options": {"min": 1, "max": 50}},
      {"name": "role",        "type": "text", "required": false, "options": {"max": 20}},
      {"name": "ticket",      "type": "text", "required": false, "options": {"max": 20}},
      {"name": "branch",      "type": "text", "required": false, "options": {"max": 200}},
      {"name": "step",        "type": "text", "required": true, "options": {"min": 1, "max": 20}},
      {"name": "pr",          "type": "number", "required": false},
      {"name": "host",        "type": "text", "required": false, "options": {"max": 100}},
      {"name": "source",      "type": "text", "required": false, "options": {"max": 20}},
      {"name": "pid",         "type": "number", "required": false},
      {"name": "started_at",  "type": "text", "required": false, "options": {"max": 30}},
      {"name": "updated_at",  "type": "text", "required": false, "options": {"max": 30}}
    ],
    "indexes": ["CREATE UNIQUE INDEX idx_session_instance ON sessions (instance_id)"],
    "listRule": "@request.auth.id != \"\"",
    "viewRule": "@request.auth.id != \"\"",
    "createRule": "@request.auth.id != \"\"",
    "updateRule": "@request.auth.id != \"\"",
    "deleteRule": "@request.auth.id != \"\""
  }' > /dev/null && echo "  sessions: OK" || echo "  sessions: already exists or error"

# Step 4: Create "milestones" collection
echo "[4/5] Creating 'milestones' collection..."
curl -sf -X POST "${PB_URL}/api/collections" \
  -H "Content-Type: application/json" \
  -H "Authorization: ${TOKEN}" \
  -d '{
    "name": "milestones",
    "type": "base",
    "schema": [
      {"name": "ticket",      "type": "text", "required": true, "options": {"max": 20}},
      {"name": "step",        "type": "text", "required": true, "options": {"max": 20}},
      {"name": "instance_id", "type": "text", "required": true, "options": {"max": 50}},
      {"name": "project",     "type": "text", "required": true, "options": {"max": 50}},
      {"name": "pr",          "type": "number", "required": false},
      {"name": "sha",         "type": "text", "required": false, "options": {"max": 40}},
      {"name": "detail",      "type": "text", "required": false, "options": {"max": 500}},
      {"name": "event_at",    "type": "text", "required": false, "options": {"max": 30}}
    ],
    "indexes": [
      "CREATE INDEX idx_milestone_ticket ON milestones (ticket)",
      "CREATE INDEX idx_milestone_created ON milestones (created)"
    ],
    "listRule": "@request.auth.id != \"\"",
    "viewRule": "@request.auth.id != \"\"",
    "createRule": "@request.auth.id != \"\"",
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
    "schema": [
      {"name": "claim_id",     "type": "text", "required": true, "options": {"min": 1, "max": 60}},
      {"name": "ticket",       "type": "text", "required": true, "options": {"max": 60}},
      {"name": "phase",        "type": "number", "required": false},
      {"name": "mega_id",      "type": "text", "required": false, "options": {"max": 20}},
      {"name": "owner",        "type": "text", "required": false, "options": {"max": 50}},
      {"name": "pid",          "type": "number", "required": false},
      {"name": "host",         "type": "text", "required": false, "options": {"max": 100}},
      {"name": "branch",       "type": "text", "required": false, "options": {"max": 200}},
      {"name": "deps",         "type": "text", "required": false, "options": {"max": 200}},
      {"name": "claimed_at",   "type": "text", "required": false, "options": {"max": 30}},
      {"name": "completed_at", "type": "text", "required": false, "options": {"max": 30}}
    ],
    "indexes": [
      "CREATE UNIQUE INDEX idx_claim_id ON claims (claim_id)",
      "CREATE INDEX idx_claim_owner ON claims (owner)",
      "CREATE INDEX idx_claim_mega ON claims (mega_id)"
    ],
    "listRule": "@request.auth.id != \"\"",
    "viewRule": "@request.auth.id != \"\"",
    "createRule": "@request.auth.id != \"\"",
    "updateRule": "@request.auth.id != \"\"",
    "deleteRule": "@request.auth.id != \"\""
  }' > /dev/null && echo "  claims: OK" || echo "  claims: already exists or error"

echo ""
echo "=== Setup Complete ==="
echo "Admin UI: ${PB_URL}/_/"
echo "API: ${PB_URL}/api/collections/{sessions,milestones,claims}/records"
