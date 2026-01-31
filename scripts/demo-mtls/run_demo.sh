#!/bin/bash
# mTLS Demo Orchestrator (CAB-1025)
#
# Usage:
#   ./scripts/demo-mtls/run_demo.sh [scenario]
#
# Scenarios:
#   full          Seed → warm-up → rotation → burst (default)
#   traffic-only  Just traffic generation
#   rotation      Rotate a random expiring client

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()   { echo -e "${GREEN}[DEMO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Config (override via env)
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
API_URL="${API_URL:-http://localhost:8000}"
DB_URL="${DB_URL:-postgresql+asyncpg://stoa:stoa@localhost:5432/stoa}"
ENDPOINT="${ENDPOINT:-/health}"
PYTHON="${PYTHON:-python3}"

# Check dependencies
command -v "$PYTHON" >/dev/null 2>&1 || error "Python3 required"

SCENARIO="${1:-full}"

banner() {
    echo -e "\n${BOLD}${CYAN}╔════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${CYAN}║   STOA mTLS Demo — Feb 26, 2026       ║${NC}"
    echo -e "${BOLD}${CYAN}╚════════════════════════════════════════╝${NC}\n"
}

seed_clients() {
    log "Seeding 100 demo clients..."
    "$PYTHON" "$PROJECT_ROOT/control-plane-api/scripts/seed_demo_clients.py"
}

run_traffic() {
    local tps="${1:-10}"
    local duration="${2:-60}"
    log "Starting traffic: ${tps} TPS for ${duration}s → ${GATEWAY_URL}${ENDPOINT}"
    "$PYTHON" "$SCRIPT_DIR/generate_traffic.py" \
        --tps "$tps" \
        --duration "$duration" \
        --gateway-url "$GATEWAY_URL" \
        --endpoint "$ENDPOINT" \
        --db-url "$DB_URL"
}

rotate_random_client() {
    log "Rotating a random expiring client..."
    # Pick a client expiring within 30 days
    CLIENT_ID=$("$PYTHON" -c "
import asyncio, os, sys
sys.path.insert(0, '$PROJECT_ROOT/control-plane-api')
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

async def pick():
    engine = create_async_engine('$DB_URL', echo=False)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        r = await s.execute(text('''
            SELECT id FROM clients
            WHERE tenant_id = 'acme' AND status = 'active'
              AND certificate_not_after < NOW() + INTERVAL '30 days'
            ORDER BY RANDOM() LIMIT 1
        '''))
        row = r.first()
        print(row[0] if row else '')
    await engine.dispose()

asyncio.run(pick())
")

    if [ -z "$CLIENT_ID" ]; then
        warn "No expiring clients found. Picking any active client."
        CLIENT_ID=$("$PYTHON" -c "
import asyncio, sys
sys.path.insert(0, '$PROJECT_ROOT/control-plane-api')
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

async def pick():
    engine = create_async_engine('$DB_URL', echo=False)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        r = await s.execute(text('''
            SELECT id FROM clients
            WHERE tenant_id = 'acme' AND status = 'active'
            ORDER BY RANDOM() LIMIT 1
        '''))
        row = r.first()
        print(row[0] if row else '')
    await engine.dispose()

asyncio.run(pick())
")
    fi

    if [ -z "$CLIENT_ID" ]; then
        error "No clients found in database. Run seed first."
    fi

    log "Rotating client: $CLIENT_ID"
    curl -s -X POST "${API_URL}/v1/clients/${CLIENT_ID}/rotate" \
        -H "Content-Type: application/json" \
        -d '{"grace_period_hours": 1, "reason": "Demo rotation"}' \
        | "$PYTHON" -m json.tool 2>/dev/null || warn "Rotation API call failed (is API running?)"
    echo ""
}

case "$SCENARIO" in
    full)
        banner
        log "=== FULL DEMO SEQUENCE ==="
        echo ""

        log "Step 1/4: Seed clients"
        seed_clients
        echo ""

        log "Step 2/4: Warm-up traffic (30s, 5 TPS)"
        run_traffic 5 30
        echo ""

        log "Step 3/4: Live certificate rotation"
        rotate_random_client
        echo ""

        log "Step 4/4: Burst traffic (60s, 20 TPS)"
        run_traffic 20 60
        echo ""

        log "=== DEMO COMPLETE ==="
        ;;

    traffic-only)
        banner
        log "=== TRAFFIC ONLY ==="
        run_traffic "${2:-10}" "${3:-120}"
        ;;

    rotation)
        banner
        log "=== ROTATION DEMO ==="
        rotate_random_client
        ;;

    *)
        echo "Usage: $0 [full|traffic-only|rotation]"
        echo ""
        echo "Scenarios:"
        echo "  full           Seed → warm-up → rotation → burst (default)"
        echo "  traffic-only   Just traffic: $0 traffic-only [TPS] [DURATION]"
        echo "  rotation       Rotate a random expiring client"
        echo ""
        echo "Environment:"
        echo "  GATEWAY_URL    MCP Gateway URL (default: http://localhost:8080)"
        echo "  API_URL        Control Plane API URL (default: http://localhost:8000)"
        echo "  DB_URL         Database URL (default: postgresql+asyncpg://...)"
        echo "  ENDPOINT       Target endpoint (default: /health)"
        exit 1
        ;;
esac
