#!/usr/bin/env bash
# Teardown K3s Gateway Cluster — restores nodes to clean state
set -euo pipefail

CP_IP="144.91.73.37"
WORKER_IP="164.68.121.123"
SSH_KEY="$HOME/.ssh/id_ed25519_stoa"
SSH="ssh -i $SSH_KEY hegemon"

echo "=== Uninstall K3s Server (CP) ==="
$SSH@$CP_IP "sudo /usr/local/bin/k3s-uninstall.sh 2>/dev/null || echo 'not installed'"

echo "=== Uninstall K3s Agent (Worker) ==="
$SSH@$WORKER_IP "sudo /usr/local/bin/k3s-agent-uninstall.sh 2>/dev/null || echo 'not installed'"

echo "=== Stop Caddy ==="
$SSH@$WORKER_IP "sudo systemctl stop caddy 2>/dev/null; sudo systemctl disable caddy 2>/dev/null || true"

echo "=== Remove kubeconfig ==="
rm -f "$HOME/.kube/config-k3s-gateways"

echo "=== Remove ArgoCD apps (run on OVH) ==="
echo "  KUBECONFIG=~/.kube/config-stoa-ovh kubectl delete application gateways-dev gateways-rec -n argocd"
echo "  KUBECONFIG=~/.kube/config-stoa-ovh kubectl delete secret k3s-gateways-cluster -n argocd"

echo ""
echo "✅ K3s cluster torn down. Nodes back to clean state."
