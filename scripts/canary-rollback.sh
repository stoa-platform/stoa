#!/bin/bash
# MCP Gateway Canary Rollback Script
# Emergency rollback - routes all traffic back to Python gateway
#
# Usage:
#   ./scripts/canary-rollback.sh
#
# This script:
# 1. Sets canary weight to 0% (all traffic to Python)
# 2. Optionally scales down Rust gateway pods

set -euo pipefail

NAMESPACE="${NAMESPACE:-stoa-system}"
INGRESS_NAME="mcp-gateway-canary"
RUST_DEPLOYMENT="mcp-gateway-rust"

echo "==============================================="
echo "  MCP GATEWAY CANARY ROLLBACK"
echo "==============================================="
echo ""
echo "Setting canary weight to 0% (all traffic to Python gateway)"
echo ""

# Get current weight
CURRENT_WEIGHT=$(kubectl get ingress "${INGRESS_NAME}" -n "${NAMESPACE}" \
    -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}' 2>/dev/null || echo "unknown")

echo "Current weight: ${CURRENT_WEIGHT}%"
echo ""

# Set weight to 0
kubectl patch ingress "${INGRESS_NAME}" -n "${NAMESPACE}" \
    -p '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/canary-weight":"0"}}}'

echo "Canary weight set to 0%"
echo ""

# Verify
NEW_WEIGHT=$(kubectl get ingress "${INGRESS_NAME}" -n "${NAMESPACE}" \
    -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}')

if [ "${NEW_WEIGHT}" == "0" ]; then
    echo "Rollback complete - all traffic now goes to Python gateway"
else
    echo "Warning: Expected weight 0% but got ${NEW_WEIGHT}%"
    echo "Manual intervention may be required!"
    exit 1
fi

echo ""
echo "==============================================="

# Optional: Scale down Rust pods
echo ""
read -p "Scale down Rust gateway pods? (y/N) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Get current replicas
    CURRENT_REPLICAS=$(kubectl get deployment "${RUST_DEPLOYMENT}" -n "${NAMESPACE}" \
        -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")

    echo "Current Rust gateway replicas: ${CURRENT_REPLICAS}"

    kubectl scale deployment "${RUST_DEPLOYMENT}" -n "${NAMESPACE}" --replicas=0

    echo "Rust gateway scaled to 0 replicas"
    echo ""
    echo "To restore Rust gateway:"
    echo "  kubectl scale deployment ${RUST_DEPLOYMENT} -n ${NAMESPACE} --replicas=${CURRENT_REPLICAS}"
fi

echo ""
echo "==============================================="
echo "  ROLLBACK SUMMARY"
echo "==============================================="
echo "  - Canary weight: 0%"
echo "  - Python gateway: Handling all traffic"
echo "  - Rust gateway: No traffic"
echo ""
echo "Next steps:"
echo "  1. Investigate the issue"
echo "  2. Check logs: kubectl logs -l app=mcp-gateway-rust -n ${NAMESPACE}"
echo "  3. Check metrics: mcp_request_errors_total{gateway=\"rust\"}"
echo "  4. When ready, resume with: ./scripts/canary-update.sh 1"
echo "==============================================="
