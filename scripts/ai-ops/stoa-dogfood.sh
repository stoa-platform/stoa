#!/bin/bash
# stoa-dogfood — Run STOA Gateway locally as LLM API proxy (CAB-1568)
#
# This script starts the gateway in proxy mode to route Claude Code API calls
# through STOA, enabling per-pane metering, budget caps, and kill-switch.
#
# Architecture:
#   Claude Code (tmux panes) → localhost:8080/v1/messages → STOA Gateway
#     → api.anthropic.com/v1/messages (with real API key)
#     → POST usage to api.gostoa.dev/api/v1/usage/record (async metering)
#
# Prerequisites:
#   1. Build the gateway: cd stoa-gateway && cargo build --release
#   2. Set ANTHROPIC_API_KEY (real upstream key)
#   3. Create applications on api.gostoa.dev (see --setup flag)
#
# Usage:
#   ./scripts/ai-ops/stoa-dogfood.sh              # Start gateway
#   ./scripts/ai-ops/stoa-dogfood.sh --setup       # Create CP apps first
#   ./scripts/ai-ops/stoa-dogfood.sh --env         # Print env vars for panes
#   ./scripts/ai-ops/stoa-dogfood.sh --stop        # Stop gateway
#
set -euo pipefail

STOA_DIR="${STOA_DIR:-$HOME/hlfh-repos/stoa}"
GATEWAY_BIN="${STOA_DIR}/stoa-gateway/target/release/stoa-gateway"
GATEWAY_PORT="${STOA_GATEWAY_PORT:-8080}"
CP_URL="${STOA_CP_URL:-https://api.gostoa.dev}"
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"
CP_API_KEY="${STOA_CONTROL_PLANE_API_KEY:-}"
PID_FILE="/tmp/stoa-dogfood.pid"

# Pane roles that get their own STOA subscription
ROLES=(ORCHESTRE BACKEND FRONTEND AUTH MCP QA)

die() { echo "ERROR: $*" >&2; exit 1; }

cmd_start() {
    [[ -n "$ANTHROPIC_KEY" ]] || die "ANTHROPIC_API_KEY not set"
    [[ -f "$GATEWAY_BIN" ]] || die "Gateway binary not found. Run: cd stoa-gateway && cargo build --release"

    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Gateway already running (PID $(cat "$PID_FILE"))"
        return 0
    fi

    echo "Starting STOA Gateway (LLM proxy mode) on :${GATEWAY_PORT}..."

    STOA_PORT="$GATEWAY_PORT" \
    STOA_MODE="proxy" \
    STOA_LLM_PROXY_ENABLED="true" \
    STOA_LLM_PROXY_UPSTREAM_URL="https://api.anthropic.com" \
    STOA_LLM_PROXY_API_KEY="$ANTHROPIC_KEY" \
    STOA_LLM_PROXY_TIMEOUT_SECS="300" \
    STOA_LLM_PROXY_METERING_URL="$CP_URL" \
    STOA_CONTROL_PLANE_URL="$CP_URL" \
    STOA_CONTROL_PLANE_API_KEY="${CP_API_KEY}" \
    STOA_ADMIN_API_TOKEN="dogfood-local" \
    RUST_LOG="stoa_gateway=info,tower_http=warn" \
    nohup "$GATEWAY_BIN" > /tmp/stoa-dogfood.log 2>&1 &

    echo $! > "$PID_FILE"
    sleep 1

    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Gateway started (PID $(cat "$PID_FILE")), port $GATEWAY_PORT"
        echo "Logs: tail -f /tmp/stoa-dogfood.log"
        echo ""
        echo "Test: curl -s http://localhost:${GATEWAY_PORT}/health"
    else
        echo "Gateway failed to start. Check /tmp/stoa-dogfood.log"
        cat /tmp/stoa-dogfood.log | tail -20
        exit 1
    fi
}

cmd_stop() {
    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "Gateway stopped (PID $PID)"
        else
            echo "Gateway not running (stale PID file)"
        fi
        rm -f "$PID_FILE"
    else
        echo "No PID file found"
    fi
}

cmd_env() {
    echo "# Add these to each tmux pane to route Claude Code through STOA Gateway:"
    echo "# (Replace STOA_API_KEY_xxx with the per-pane key from --setup)"
    echo ""
    for role in "${ROLES[@]}"; do
        role_lower=$(echo "$role" | tr '[:upper:]' '[:lower:]')
        echo "# ${role} pane:"
        echo "export ANTHROPIC_BASE_URL=http://localhost:${GATEWAY_PORT}"
        echo "export ANTHROPIC_API_KEY=\${STOA_KEY_${role}}  # per-pane STOA key"
        echo ""
    done
    echo "# Or set globally (all panes share one key — less granular):"
    echo "export ANTHROPIC_BASE_URL=http://localhost:${GATEWAY_PORT}"
}

cmd_setup() {
    echo "=== STOA Dogfood Setup ==="
    echo ""
    echo "Create applications and subscriptions on ${CP_URL} for each pane."
    echo "Use the Console UI (console.gostoa.dev) or API calls:"
    echo ""
    for role in "${ROLES[@]}"; do
        role_lower=$(echo "$role" | tr '[:upper:]' '[:lower:]')
        echo "  Application: ai-factory-${role_lower}"
        echo "    → Create subscription → get API key → export STOA_KEY_${role}=<key>"
        echo ""
    done
    echo "Or create via API:"
    echo '  curl -X POST ${CP_URL}/api/v1/applications \\'
    echo '    -H "Authorization: Bearer $TOKEN" \\'
    echo '    -H "Content-Type: application/json" \\'
    echo '    -d '"'"'{"name": "ai-factory-backend", "description": "BACKEND pane"}'"'"
    echo ""
    echo "After creating apps, run: $0 --env"
}

# --- Main ---
case "${1:-}" in
    --stop)   cmd_stop ;;
    --env)    cmd_env ;;
    --setup)  cmd_setup ;;
    --help|-h)
        echo "Usage: $0 [--start|--stop|--env|--setup]"
        echo "  (default)  Start the gateway"
        echo "  --stop     Stop the gateway"
        echo "  --env      Print env vars for tmux panes"
        echo "  --setup    Show setup instructions for CP apps"
        ;;
    *)        cmd_start ;;
esac
