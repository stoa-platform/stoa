#!/usr/bin/env bash
# =============================================================================
# STOA Platform — mTLS Test Certificate Generator (CAB-864)
# =============================================================================
# !! DEMO ONLY — NOT FOR PRODUCTION USE !!
# These certificates are self-signed, short-lived, and use demo-only keys.
# Never deploy these in any production or staging environment.
# =============================================================================
# Generates a demo CA + 100 client certificates for the mTLS demo scenario.
# Certificates are signed by the demo CA with proper Subject DNs.
#
# Usage:
#   ./scripts/demo/generate-mtls-certs.sh              # Generate 100 certs
#   ./scripts/demo/generate-mtls-certs.sh --count 10   # Generate 10 certs
#   ./scripts/demo/generate-mtls-certs.sh --clean       # Remove all generated certs
#
# Output: scripts/demo/certs/
#   stoa-demo-ca.pem, stoa-demo-ca-key.pem   — Root CA
#   client-001.pem, client-001-key.pem        — Client cert + key
#   ...
#   client-100.pem, client-100-key.pem
#   fingerprints.csv                          — external_id,fingerprint_hex,fingerprint_b64url
# =============================================================================

set -euo pipefail

# ============================================================================
# Pre-flight: openssl version check
# ============================================================================
if ! command -v openssl &>/dev/null; then
  echo "[FATAL] openssl not found. Install: brew install openssl (macOS) or apt install openssl (Linux)"
  exit 1
fi

OPENSSL_VERSION=$(openssl version 2>&1)
OPENSSL_MAJOR=$(echo "$OPENSSL_VERSION" | grep -oE '[0-9]+\.[0-9]+' | head -1)
echo "[INFO] Using: $OPENSSL_VERSION"

# Require OpenSSL 1.1+ or LibreSSL 2.8+ (for SHA-256 support)
case "$OPENSSL_VERSION" in
  OpenSSL\ 0.*|OpenSSL\ 1.0.*)
    echo "[FATAL] OpenSSL >= 1.1.0 required (found: $OPENSSL_VERSION)"
    echo "        macOS: brew install openssl && export PATH=\"\$(brew --prefix openssl)/bin:\$PATH\""
    exit 1
    ;;
  LibreSSL\ [01].*|LibreSSL\ 2.[0-7].*)
    echo "[FATAL] LibreSSL >= 2.8.0 required (found: $OPENSSL_VERSION)"
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="${MTLS_CERTS_DIR:-$SCRIPT_DIR/certs}"
COUNT=100
CLEAN=false

# Parse args
for arg in "$@"; do
  case $arg in
    --count=*) COUNT="${arg#*=}" ;;
    --count)   shift; COUNT="${2:-100}" ;;
    --clean)   CLEAN=true ;;
    --help|-h)
      echo "Usage: $0 [--count N] [--clean]"
      echo "  --count N   Number of client certs to generate (default: 100)"
      echo "  --clean     Remove all generated certs"
      exit 0
      ;;
  esac
done

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'
log()  { echo -e "${GREEN}[CERTS]${NC} $*"; }
info() { echo -e "${BLUE}[INFO]${NC} $*"; }

if [ "$CLEAN" = true ]; then
  log "Cleaning $CERTS_DIR..."
  rm -rf "$CERTS_DIR"
  log "Done."
  exit 0
fi

# Company names for variety (anonymized, no real clients per opsec.md)
COMPANIES=("Acme Corp" "Nova Industries" "Apex Digital" "Meridian Services" "Zenith Solutions"
           "Quantum Labs" "Atlas Technologies" "Vanguard Systems" "Pinnacle Group" "Stratos Inc")

mkdir -p "$CERTS_DIR"

# ============================================================================
# Step 1: Generate Root CA
# ============================================================================
if [ -f "$CERTS_DIR/stoa-demo-ca.pem" ]; then
  log "CA already exists — skipping generation"
else
  log "Generating Root CA..."
  openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 \
    -nodes -keyout "$CERTS_DIR/stoa-demo-ca-key.pem" \
    -out "$CERTS_DIR/stoa-demo-ca.pem" \
    -subj "/CN=STOA Demo CA/O=STOA Platform/C=FR" \
    2>/dev/null
  log "CA created: $CERTS_DIR/stoa-demo-ca.pem"
fi

# ============================================================================
# Step 2: Generate Client Certificates
# ============================================================================
log "Generating $COUNT client certificates..."

# CSV header
echo "external_id,fingerprint_hex,fingerprint_b64url,subject_dn,company" > "$CERTS_DIR/fingerprints.csv"

for i in $(seq 1 "$COUNT"); do
  NUM=$(printf "%03d" "$i")
  EXTERNAL_ID="api-consumer-$NUM"
  COMPANY="${COMPANIES[$(( (i - 1) % ${#COMPANIES[@]} ))]}"
  CERT_FILE="$CERTS_DIR/client-$NUM.pem"
  KEY_FILE="$CERTS_DIR/client-$NUM-key.pem"
  SUBJECT_DN="/CN=$EXTERNAL_ID/OU=tenant-acme/O=$COMPANY/C=FR"

  if [ -f "$CERT_FILE" ]; then
    # Already exists — just compute fingerprint for CSV
    :
  else
    # Generate CSR + sign with CA
    openssl req -newkey rsa:2048 -sha256 -nodes \
      -keyout "$KEY_FILE" \
      -out "$CERTS_DIR/client-$NUM.csr" \
      -subj "$SUBJECT_DN" \
      2>/dev/null

    openssl x509 -req -sha256 -days 730 \
      -in "$CERTS_DIR/client-$NUM.csr" \
      -CA "$CERTS_DIR/stoa-demo-ca.pem" \
      -CAkey "$CERTS_DIR/stoa-demo-ca-key.pem" \
      -CAcreateserial \
      -out "$CERT_FILE" \
      2>/dev/null

    # Clean up CSR
    rm -f "$CERTS_DIR/client-$NUM.csr"
  fi

  # Compute fingerprints (SHA-256 of DER)
  FINGERPRINT_HEX=$(openssl x509 -in "$CERT_FILE" -outform DER 2>/dev/null | openssl dgst -sha256 -hex 2>/dev/null | awk '{print $NF}')
  FINGERPRINT_B64URL=$(openssl x509 -in "$CERT_FILE" -outform DER 2>/dev/null | openssl dgst -sha256 -binary 2>/dev/null | base64 | tr '+/' '-_' | tr -d '=')

  echo "$EXTERNAL_ID,$FINGERPRINT_HEX,$FINGERPRINT_B64URL,CN=$EXTERNAL_ID OU=tenant-acme O=$COMPANY C=FR,$COMPANY" >> "$CERTS_DIR/fingerprints.csv"

  # Progress every 25 certs
  if [ $((i % 25)) -eq 0 ]; then
    info "  $i/$COUNT certificates generated..."
  fi
done

# Clean up serial file
rm -f "$CERTS_DIR/stoa-demo-ca.srl"

log "Done! $COUNT client certificates in $CERTS_DIR/"
info "CA:           $CERTS_DIR/stoa-demo-ca.pem"
info "Clients:      $CERTS_DIR/client-001.pem ... client-$(printf '%03d' "$COUNT").pem"
info "Fingerprints: $CERTS_DIR/fingerprints.csv"
info ""
info "Quick verify:"
info "  openssl x509 -in $CERTS_DIR/client-001.pem -text -noout | head -15"
info "  openssl verify -CAfile $CERTS_DIR/stoa-demo-ca.pem $CERTS_DIR/client-001.pem"
