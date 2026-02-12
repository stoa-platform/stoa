#!/usr/bin/env bash
# Deploy Fluent Bit DaemonSet for shipping gateway access logs to OpenSearch.
# Idempotent — safe to re-run.
#
# Prerequisites:
#   - kubectl configured with OVH kubeconfig
#   - stoa-opensearch-secret exists in logging namespace (or create it):
#     kubectl create secret generic stoa-opensearch-secret -n logging \
#       --from-literal=OPENSEARCH_PASSWORD='<admin-password>'
#
# Usage: ./k8s/logging/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Deploying Fluent Bit log pipeline ==="

# 1. Namespace
echo "[1/4] Creating namespace..."
kubectl apply -f "$SCRIPT_DIR/namespace.yaml"

# 2. RBAC
echo "[2/4] Applying RBAC..."
kubectl apply -f "$SCRIPT_DIR/fluent-bit-rbac.yaml"

# 3. ConfigMap
echo "[3/4] Applying ConfigMap..."
kubectl apply -f "$SCRIPT_DIR/fluent-bit-config.yaml"

# 4. DaemonSet
echo "[4/4] Deploying DaemonSet..."
kubectl apply -f "$SCRIPT_DIR/fluent-bit-daemonset.yaml"

echo ""
echo "=== Fluent Bit deployed ==="
echo "Check status: kubectl get ds -n logging fluent-bit"
echo "Check logs:   kubectl logs -n logging -l app=fluent-bit --tail=20"
