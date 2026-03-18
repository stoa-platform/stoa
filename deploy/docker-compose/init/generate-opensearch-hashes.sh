#!/bin/sh
# =============================================================================
# Generate bcrypt hashes for OpenSearch internal users (dev environment)
# =============================================================================
# Runs BEFORE OpenSearch starts. Writes internal_users.yml with proper hashes
# to a shared volume so OpenSearch can load them on first boot.
# Uses OpenSearch's own hash.sh tool (bundled in the image).
# =============================================================================

set -e

HASH_TOOL="/usr/share/opensearch/plugins/opensearch-security/tools/hash.sh"
OUTPUT_DIR="/output/security"
SOURCE_DIR="/input/security"
OS_UID=$(id -u)
OS_GID=$(id -g)

log() { echo "[HASH-GEN] $1"; }

# Copy all base security config files from source (mounted :ro)
log "Copying base security config..."
mkdir -p "$OUTPUT_DIR"
cp "$SOURCE_DIR"/*.yml "$OUTPUT_DIR/" 2>/dev/null || true
chmod 644 "$OUTPUT_DIR"/*.yml 2>/dev/null || true

# Generate bcrypt hashes
if [ ! -f "$HASH_TOOL" ]; then
  log "ERROR: hash.sh not found at $HASH_TOOL"
  exit 1
fi
chmod +x "$HASH_TOOL"

ADMIN_PW="${OPENSEARCH_ADMIN_PASSWORD:?OPENSEARCH_ADMIN_PASSWORD required}"
DASHBOARDS_PW="${OPENSEARCH_DASHBOARDS_PASSWORD:-kibanaserver}"
LOGWRITER_PW="${OPENSEARCH_LOGWRITER_PASSWORD:-logwriter}"

log "Generating admin hash..."
ADMIN_HASH=$("$HASH_TOOL" -p "$ADMIN_PW" 2>/dev/null | tail -1)

log "Generating kibanaserver hash..."
DASHBOARDS_HASH=$("$HASH_TOOL" -p "$DASHBOARDS_PW" 2>/dev/null | tail -1)

log "Generating logwriter hash..."
LOGWRITER_HASH=$("$HASH_TOOL" -p "$LOGWRITER_PW" 2>/dev/null | tail -1)

log "Writing internal_users.yml with generated hashes"
cat > "$OUTPUT_DIR/internal_users.yml" <<EOF
_meta:
  type: "internalusers"
  config_version: 2

admin:
  hash: "${ADMIN_HASH}"
  reserved: true
  backend_roles:
    - "admin"
  description: "OpenSearch admin user"

kibanaserver:
  hash: "${DASHBOARDS_HASH}"
  reserved: true
  description: "OpenSearch Dashboards internal service account"

logwriter:
  hash: "${LOGWRITER_HASH}"
  reserved: false
  backend_roles:
    - "logwriter"
  description: "Fluent-Bit log shipping account"
EOF

# Ensure OpenSearch user (1000:1000) can read the config
chown -R 1000:1000 "$OUTPUT_DIR" 2>/dev/null || true
chmod 644 "$OUTPUT_DIR"/*.yml 2>/dev/null || true

log "Done. Security config ready at $OUTPUT_DIR/"
ls -la "$OUTPUT_DIR/"
