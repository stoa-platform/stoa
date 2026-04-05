#!/bin/bash
# backup-keycloak.sh — Export KC realm before destructive operations
#
# Exports the full stoa realm (users, credentials, clients, scopes) to a
# timestamped JSON file. The export includes hashed credentials, so users
# keep their current passwords when you reimport.
#
# Usage:
#   ./scripts/backup-keycloak.sh                    # from deploy/docker-compose/
#   ./deploy/docker-compose/scripts/backup-keycloak.sh  # from repo root
#
# Restore:
#   Copy the backup into the import dir and restart KC:
#   cp backups/keycloak-stoa-YYYY-MM-DD-HHMMSS.json init/keycloak-realm.json
#   docker compose up -d keycloak --force-recreate

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REALM="${KC_REALM:-stoa}"
KC_URL="${KC_INTERNAL_URL:-http://localhost:8080}"
KC_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KC_ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
CONTAINER="${KC_CONTAINER:-stoa-keycloak}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/../backups"
TIMESTAMP=$(date +%Y-%m-%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/keycloak-${REALM}-${TIMESTAMP}.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Pre-checks
# ---------------------------------------------------------------------------
mkdir -p "$BACKUP_DIR"

echo "Checking Keycloak availability..."
if ! curl -sf "${KC_URL}/realms/${REALM}" > /dev/null 2>&1; then
  echo -e "${RED}ERROR: Keycloak not reachable at ${KC_URL}/realms/${REALM}${NC}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------
docker exec "$CONTAINER" /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 --realm master \
  --user "$KC_ADMIN" --password "$KC_ADMIN_PASS" 2>/dev/null

# ---------------------------------------------------------------------------
# Export realm via KC container
# ---------------------------------------------------------------------------
echo "Exporting realm '${REALM}'..."

# Use kc.sh export inside the container (includes credentials)
docker exec "$CONTAINER" /opt/keycloak/bin/kc.sh export \
  --dir /tmp/kc-export \
  --realm "$REALM" \
  --users realm_file 2>/dev/null

# Copy the export out of the container
docker cp "${CONTAINER}:/tmp/kc-export/${REALM}-realm.json" "$BACKUP_FILE" 2>/dev/null

# Cleanup inside container
docker exec "$CONTAINER" rm -rf /tmp/kc-export 2>/dev/null

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
if [ ! -f "$BACKUP_FILE" ]; then
  echo -e "${RED}ERROR: Export failed — no file created${NC}"
  exit 1
fi

USER_COUNT=$(python3 -c "
import json
with open('$BACKUP_FILE') as f:
    data = json.load(f)
users = data.get('users', [])
print(len(users))
" 2>/dev/null || echo "?")

SCOPE_COUNT=$(python3 -c "
import json
with open('$BACKUP_FILE') as f:
    data = json.load(f)
scopes = data.get('clientScopes', [])
print(len(scopes))
" 2>/dev/null || echo "?")

FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)

echo ""
echo -e "${GREEN}Backup created:${NC} ${BACKUP_FILE}"
echo "  Size:    ${FILE_SIZE}"
echo "  Users:   ${USER_COUNT}"
echo "  Scopes:  ${SCOPE_COUNT}"
echo ""
echo -e "${YELLOW}To restore:${NC}"
echo "  cp '${BACKUP_FILE}' '${SCRIPT_DIR}/../init/keycloak-realm.json'"
echo "  docker compose down keycloak"
echo "  docker compose exec postgres psql -U stoa -d postgres -c 'DROP DATABASE keycloak; CREATE DATABASE keycloak OWNER stoa;'"
echo "  docker compose up -d keycloak"
