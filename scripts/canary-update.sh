#!/bin/bash
# MCP Gateway Canary Weight Update Script
# Updates the traffic split between Python and Rust gateways
#
# Usage:
#   ./scripts/canary-update.sh <weight>
#
# Examples:
#   ./scripts/canary-update.sh 0     # All traffic to Python (disable canary)
#   ./scripts/canary-update.sh 1     # 1% to Rust
#   ./scripts/canary-update.sh 5     # 5% to Rust
#   ./scripts/canary-update.sh 50    # 50/50 split
#   ./scripts/canary-update.sh 100   # All traffic to Rust

set -euo pipefail

NAMESPACE="${NAMESPACE:-stoa-system}"
INGRESS_NAME="mcp-gateway-canary"

usage() {
    echo "Usage: $0 <weight>"
    echo "  weight: 0-100 (percentage of traffic to Rust gateway)"
    echo ""
    echo "Examples:"
    echo "  $0 0     # All traffic to Python (disable canary)"
    echo "  $0 1     # 1% to Rust"
    echo "  $0 5     # 5% to Rust"
    echo "  $0 50    # 50/50 split"
    echo "  $0 100   # All traffic to Rust"
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

WEIGHT=$1

if ! [[ "$WEIGHT" =~ ^[0-9]+$ ]] || [ "$WEIGHT" -lt 0 ] || [ "$WEIGHT" -gt 100 ]; then
    echo "Error: Weight must be a number between 0 and 100"
    exit 1
fi

echo "Updating canary weight to ${WEIGHT}%..."
echo "  Namespace: ${NAMESPACE}"
echo "  Ingress: ${INGRESS_NAME}"
echo ""

# Get current weight for logging
CURRENT_WEIGHT=$(kubectl get ingress "${INGRESS_NAME}" -n "${NAMESPACE}" \
    -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}' 2>/dev/null || echo "unknown")

echo "Current weight: ${CURRENT_WEIGHT}%"
echo "New weight: ${WEIGHT}%"
echo ""

# Update canary weight
kubectl patch ingress "${INGRESS_NAME}" -n "${NAMESPACE}" \
    -p "{\"metadata\":{\"annotations\":{\"nginx.ingress.kubernetes.io/canary-weight\":\"${WEIGHT}\"}}}"

echo ""
echo "Canary weight updated to ${WEIGHT}%"
echo ""

# Verify update
NEW_WEIGHT=$(kubectl get ingress "${INGRESS_NAME}" -n "${NAMESPACE}" \
    -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}')

if [ "${NEW_WEIGHT}" == "${WEIGHT}" ]; then
    echo "Verified: Canary weight is now ${NEW_WEIGHT}%"
else
    echo "Warning: Expected weight ${WEIGHT}% but got ${NEW_WEIGHT}%"
    exit 1
fi

echo ""
echo "Traffic distribution:"
echo "  Python gateway: $((100 - WEIGHT))%"
echo "  Rust gateway: ${WEIGHT}%"
echo ""
echo "Monitor metrics at:"
echo "  - Grafana: https://grafana.gostoa.dev/d/mcp-gateway-migration"
echo "  - Prometheus: mcp_shadow_match_total, mcp_request_errors_total"
