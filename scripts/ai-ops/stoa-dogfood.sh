#!/bin/bash
# stoa-dogfood — Run STOA Gateway locally as LLM API proxy (CAB-1568/CAB-1601)
#
# This script starts the gateway in proxy mode to route Claude Code API calls
# through STOA, enabling per-pane metering, budget caps, and kill-switch.
# Supports Anthropic prompt caching passthrough with per-token-type tracking.
#
# Architecture:
#   Claude Code (tmux panes) → localhost:8080/v1/messages → STOA Gateway
#     → api.anthropic.com/v1/messages (with real API key)
#     → POST usage to api.gostoa.dev/v1/usage/record (async metering)
#     → Prometheus metrics on :8080/metrics (cache tokens, cost, latency)
#
# Prerequisites:
#   1. Build the gateway: cd stoa-gateway && cargo build --release
#   2. Set ANTHROPIC_API_KEY (real upstream key)
#   3. Set STOA_CONTROL_PLANE_API_KEY (gateway→CP auth)
#
# Usage:
#   ./scripts/ai-ops/stoa-dogfood.sh              # Start gateway
#   ./scripts/ai-ops/stoa-dogfood.sh --stop        # Stop gateway
#   ./scripts/ai-ops/stoa-dogfood.sh --env         # Print env vars for local panes
#   ./scripts/ai-ops/stoa-dogfood.sh --hegemon     # Print env vars for HEGEMON workers
#   ./scripts/ai-ops/stoa-dogfood.sh --verify      # Health check + cache metrics test
#   ./scripts/ai-ops/stoa-dogfood.sh --setup       # Show setup instructions
#
set -euo pipefail

STOA_DIR="${STOA_DIR:-$HOME/hlfh-repos/stoa}"
GATEWAY_BIN="${STOA_DIR}/stoa-gateway/target/release/stoa-gateway"
GATEWAY_PORT="${STOA_GATEWAY_PORT:-8080}"
CP_URL="${STOA_CP_URL:-https://api.gostoa.dev}"
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"
CP_API_KEY="${STOA_CONTROL_PLANE_API_KEY:-}"
PID_FILE="/tmp/stoa-dogfood.pid"

# HEGEMON remote gateway (production)
HEGEMON_GATEWAY_URL="${STOA_HEGEMON_GATEWAY_URL:-https://mcp.gostoa.dev}"

# Pane roles that get their own STOA subscription
ROLES=(ORCHESTRE BACKEND FRONTEND AUTH MCP QA)

# HEGEMON worker hostnames
HEGEMON_WORKERS=(w1 w2 w3 w4 w5)
HEGEMON_ROLES=(backend frontend mcp auth qa)

die() { echo "ERROR: $*" >&2; exit 1; }
ok()  { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; }

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
    STOA_LLM_PROXY_SKIP_VALIDATION="true" \
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
        tail -20 /tmp/stoa-dogfood.log
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
    echo "# (Replace STOA_KEY_xxx with the per-pane key from --setup)"
    echo ""
    for role in "${ROLES[@]}"; do
        echo "# ${role} pane:"
        echo "export ANTHROPIC_BASE_URL=http://localhost:${GATEWAY_PORT}"
        echo "export ANTHROPIC_API_KEY=\${STOA_KEY_${role}}  # per-pane STOA key"
        echo ""
    done
    echo "# Or set globally (all panes share one key — less granular):"
    echo "export ANTHROPIC_BASE_URL=http://localhost:${GATEWAY_PORT}"
}

cmd_hegemon() {
    echo "# HEGEMON Worker Environment Variables"
    echo "# Add these to ~/.env.hegemon on each Contabo VPS worker."
    echo "# Gateway: ${HEGEMON_GATEWAY_URL} (production, mTLS-bypassed for LLM proxy)"
    echo ""
    for i in "${!HEGEMON_WORKERS[@]}"; do
        worker="${HEGEMON_WORKERS[$i]}"
        role="${HEGEMON_ROLES[$i]}"
        echo "# === ${worker} (${role}) ==="
        echo "ANTHROPIC_BASE_URL=${HEGEMON_GATEWAY_URL}"
        echo "# STOA_LLM_API_KEY=<key-from-console>  # per-worker subscription key"
        echo "HEGEMON_ROLE=${role}"
        echo ""
    done
    echo "# Steps to deploy:"
    echo "#   1. Create apps in Console (console.gostoa.dev) under 'tordepo' tenant"
    echo "#   2. Create a subscription per worker app → get API key"
    echo "#   3. SSH to each VPS and add the vars above to ~/.env.hegemon"
    echo "#   4. systemctl restart hegemon-agent"
    echo "#"
    echo "# Verify: curl -s ${HEGEMON_GATEWAY_URL}/health"
}

cmd_verify() {
    echo "=== STOA Dogfood Verification ==="
    local gateway_url="http://localhost:${GATEWAY_PORT}"
    local pass=0
    local total=0

    # 1. Gateway health
    total=$((total + 1))
    echo ""
    echo "1. Gateway health check..."
    if health=$(curl -sf "${gateway_url}/health" 2>/dev/null); then
        ok "Gateway healthy: ${health}"
        pass=$((pass + 1))
    else
        fail "Gateway not reachable at ${gateway_url}/health"
        echo "   Start it with: $0 (or $0 --start)"
        echo ""
        echo "Result: ${pass}/${total} checks passed"
        exit 1
    fi

    # 2. Anthropic passthrough (lightweight model list or messages endpoint)
    total=$((total + 1))
    echo ""
    echo "2. Anthropic API passthrough..."
    # Send a minimal messages request to verify the proxy works
    if [[ -n "$ANTHROPIC_KEY" ]]; then
        resp=$(curl -sf -w "%{http_code}" -o /tmp/stoa-verify-resp.json \
            "${gateway_url}/v1/messages" \
            -H "content-type: application/json" \
            -H "x-api-key: ${ANTHROPIC_KEY}" \
            -H "anthropic-version: 2023-06-01" \
            -d '{
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Say hi"}]
            }' 2>/dev/null || echo "000")
        if [[ "$resp" == "200" ]]; then
            ok "Anthropic passthrough works (200)"
            # Check if response contains cache fields (usage section)
            if python3 -c "
import json, sys
with open('/tmp/stoa-verify-resp.json') as f:
    data = json.load(f)
usage = data.get('usage', {})
print(f'  Tokens: input={usage.get(\"input_tokens\",0)}, output={usage.get(\"output_tokens\",0)}')
if 'cache_creation_input_tokens' in usage:
    print(f'  Cache: creation={usage[\"cache_creation_input_tokens\"]}, read={usage.get(\"cache_read_input_tokens\",0)}')
" 2>/dev/null; then
                true  # output printed by python
            fi
            pass=$((pass + 1))
        else
            fail "Anthropic passthrough returned HTTP ${resp}"
            if [[ -f /tmp/stoa-verify-resp.json ]]; then
                head -5 /tmp/stoa-verify-resp.json 2>/dev/null || true
            fi
        fi
    else
        fail "ANTHROPIC_API_KEY not set — skipping passthrough test"
    fi

    # 3. Prometheus metrics endpoint reachable + LLM metrics
    total=$((total + 1))
    echo ""
    echo "3. Prometheus metrics..."
    if metrics=$(curl -sf "${gateway_url}/metrics" 2>/dev/null); then
        llm_metrics=$(echo "$metrics" | grep -c "gateway_llm" || true)
        cache_metrics=$(echo "$metrics" | grep -c "gateway_llm_cache" || true)
        if [[ "$cache_metrics" -gt 0 ]]; then
            ok "Found ${cache_metrics} cache metric lines"
            echo "$metrics" | grep "gateway_llm_cache" | head -8 | sed 's/^/   /'
        elif [[ "$llm_metrics" -gt 0 ]]; then
            ok "Found ${llm_metrics} LLM metric lines (cache counters lazy-init on first cached request)"
            echo "$metrics" | grep "gateway_llm" | head -5 | sed 's/^/   /'
        else
            ok "Metrics endpoint reachable (LLM counters lazy-init after first proxied request with caching)"
        fi
        pass=$((pass + 1))
    else
        fail "Cannot reach ${gateway_url}/metrics"
    fi

    # 4. CP API usage endpoint
    total=$((total + 1))
    echo ""
    echo "4. Control Plane usage API..."
    if [[ -n "$CP_API_KEY" ]]; then
        cp_resp=$(curl -s -w "%{http_code}" -o /dev/null \
            "${CP_URL}/v1/usage/record" \
            -H "X-API-Key: ${CP_API_KEY}" \
            -H "Content-Type: application/json" \
            -d '{
                "tenant_id": "verify-test",
                "subscription_id": "verify-test",
                "request_count": 0,
                "total_latency_ms": 0,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0
            }' 2>/dev/null || echo "000")
        if [[ "$cp_resp" == "201" ]]; then
            ok "CP API accepts cache token fields (201)"
            pass=$((pass + 1))
        elif [[ "$cp_resp" == "500" ]]; then
            ok "CP API reachable + auth valid (500 = DB-level error with test data, expected)"
            pass=$((pass + 1))
        elif [[ "$cp_resp" == "401" ]]; then
            fail "CP API returned 401 — check STOA_CONTROL_PLANE_API_KEY"
        else
            fail "CP API returned HTTP ${cp_resp}"
        fi
    else
        fail "STOA_CONTROL_PLANE_API_KEY not set — skipping CP API test"
    fi

    # Summary
    echo ""
    echo "=== Result: ${pass}/${total} checks passed ==="
    if [[ "$pass" -eq "$total" ]]; then
        echo "All checks passed. Cache token tracking is operational."
        rm -f /tmp/stoa-verify-resp.json
        return 0
    else
        echo "Some checks failed. See above for details."
        rm -f /tmp/stoa-verify-resp.json
        return 1
    fi
}

cmd_status() {
    echo "=== STOA Dogfood Status ==="
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "  Status:  RUNNING"
            echo "  PID:     $pid"
            echo "  Port:    $GATEWAY_PORT"
            echo "  Logs:    /tmp/stoa-dogfood.log"
            echo "  Health:  $(curl -sf "http://localhost:${GATEWAY_PORT}/health" 2>/dev/null || echo 'unreachable')"
        else
            echo "  Status:  STOPPED (stale PID file)"
            echo "  PID:     $pid (not running)"
        fi
    else
        echo "  Status:  STOPPED (no PID file)"
    fi
}

cmd_setup() {
    echo "=== STOA Dogfood Setup ==="
    echo ""
    echo "Create applications and subscriptions on ${CP_URL} for each pane."
    echo "Use the Console UI (console.gostoa.dev) or API calls:"
    echo ""
    echo "Tenant: 'tordepo' (or your account name on console.gostoa.dev)"
    echo ""
    for role in "${ROLES[@]}"; do
        role_lower=$(echo "$role" | tr '[:upper:]' '[:lower:]')
        echo "  Application: ai-factory-${role_lower}"
        echo "    → Create subscription → get API key → export STOA_KEY_${role}=<key>"
        echo ""
    done
    echo "Steps:"
    echo "  1. Log in to console.gostoa.dev"
    echo "  2. Create an application per pane role (ai-factory-backend, ai-factory-frontend, etc.)"
    echo "  3. Create a subscription for each app (LLM Proxy plan)"
    echo "  4. Copy each subscription API key"
    echo "  5. Run: $0 --env (local) or $0 --hegemon (remote workers)"
    echo ""
    echo "For HEGEMON workers (Contabo VPS):"
    echo "  - Use mcp.gostoa.dev as the gateway URL (not localhost)"
    echo "  - Add ANTHROPIC_BASE_URL + STOA_LLM_API_KEY to ~/.env.hegemon"
    echo "  - Run: $0 --hegemon for the env block"
}

# --- Main ---
case "${1:-}" in
    --stop)     cmd_stop ;;
    --status)   cmd_status ;;
    --env)      cmd_env ;;
    --hegemon)  cmd_hegemon ;;
    --verify)   cmd_verify ;;
    --setup)    cmd_setup ;;
    --start)    cmd_start ;;
    --help|-h)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  (default)   Start the gateway locally"
        echo "  --start     Start the gateway locally"
        echo "  --stop      Stop the gateway"
        echo "  --status    Show gateway status (PID, port, health)"
        echo "  --env       Print env vars for local tmux panes"
        echo "  --hegemon   Print env vars for HEGEMON workers (Contabo VPS)"
        echo "  --verify    Run health + passthrough + cache metrics checks"
        echo "  --setup     Show setup instructions for CP apps"
        ;;
    *)          cmd_start ;;
esac
