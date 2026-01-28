#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Cleanup
# Tears down all containers and removes volumes
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../../deploy/demo-federation"
TOKEN_DIR="${SCRIPT_DIR}/.tokens"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== STOA Federation Demo — Cleanup ===${NC}"
echo ""

docker compose -f "${COMPOSE_DIR}/docker-compose.yml" down -v

# Clean token files
rm -rf "${TOKEN_DIR}"

echo ""
echo -e "${GREEN}Federation demo cleaned up.${NC}"
