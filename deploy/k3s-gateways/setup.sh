#!/usr/bin/env bash
# K3s Gateway Cluster Setup — Contabo w1 (CP) + w2 (worker)
# Run from local machine with SSH access to both nodes.
# Prerequisites: ~/.ssh/id_ed25519_stoa, gh CLI, kubectl, GHCR PAT
set -euo pipefail

# --- Configuration ---
CP_IP="${K3S_CP_IP:?Set K3S_CP_IP}"
WORKER_IP="${K3S_WORKER_IP:?Set K3S_WORKER_IP}"
SSH_KEY="$HOME/.ssh/id_ed25519_stoa"
SSH_USER="hegemon"
SSH="ssh -i $SSH_KEY $SSH_USER"
KUBECONFIG_PATH="$HOME/.kube/config-k3s-gateways"

echo "=== Phase 1: Firewall ==="
$SSH@$CP_IP "sudo ufw allow from $WORKER_IP to any comment 'K3s worker'"
$SSH@$WORKER_IP "sudo ufw allow from $CP_IP to any comment 'K3s CP'"
$SSH@$CP_IP "sudo ufw allow 80/tcp comment 'Ingress HTTP'; sudo ufw allow 443/tcp comment 'Ingress HTTPS'"
$SSH@$WORKER_IP "sudo ufw allow 80/tcp comment 'Ingress HTTP'; sudo ufw allow 443/tcp comment 'Ingress HTTPS'"

echo "=== Phase 2: K3s Server (CP) ==="
$SSH@$CP_IP "curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='server --disable traefik --disable servicelb --tls-san $CP_IP' sudo sh -"
sleep 5
TOKEN=$($SSH@$CP_IP "sudo cat /var/lib/rancher/k3s/server/node-token")

echo "=== Phase 3: K3s Agent (Worker) ==="
$SSH@$WORKER_IP "sudo K3S_URL='https://$CP_IP:6443' K3S_TOKEN='$TOKEN' sh -c 'curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC=\"agent --node-name k3s-worker-1\" sh -'"
sleep 15

echo "=== Phase 4: Kubeconfig ==="
$SSH@$CP_IP "sudo cat /etc/rancher/k3s/k3s.yaml" | sed "s/127.0.0.1/$CP_IP/g" > "$KUBECONFIG_PATH"
export KUBECONFIG="$KUBECONFIG_PATH"
kubectl get nodes

echo "=== Phase 5: Remove Traefik (K3s sometimes installs it anyway) ==="
kubectl delete helmchart traefik traefik-crd -n kube-system --ignore-not-found
kubectl delete svc traefik -n kube-system --ignore-not-found
kubectl delete deployment traefik -n kube-system --ignore-not-found

echo "=== Phase 6: Namespaces ==="
kubectl create namespace gateway-dev --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace gateway-rec --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace gateway-dev env=dev --overwrite
kubectl label namespace gateway-rec env=rec --overwrite

echo "=== Phase 7: GHCR Pull Secret ==="
GH_TOKEN=$(gh auth token)
for ns in gateway-dev gateway-rec; do
  kubectl create secret docker-registry ghcr-creds \
    --docker-server=ghcr.io \
    --docker-username=stoa-platform \
    --docker-password="$GH_TOKEN" \
    -n "$ns" --dry-run=client -o yaml | kubectl apply -f -
done

echo "=== Phase 8: Gateway Secrets ==="
echo "⚠ Create stoa-gateway-secrets manually in both namespaces:"
echo "  kubectl create secret generic stoa-gateway-secrets \\"
echo "    --from-literal=STOA_ADMIN_API_TOKEN=<token> \\"
echo "    --from-literal=STOA_KEYCLOAK_ADMIN_PASSWORD=<password> \\"
echo "    --from-literal=STOA_CONTROL_PLANE_API_KEY=<key> \\"
echo "    -n gateway-dev"
echo "  (repeat for gateway-rec)"

echo "=== Phase 9: Ingress NGINX ==="
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/baremetal/deploy.yaml
# Change to ClusterIP (Caddy handles external traffic)
sleep 15
kubectl patch svc ingress-nginx-controller -n ingress-nginx \
  -p '{"spec":{"type":"ClusterIP","ports":[{"port":80,"targetPort":"http","name":"http"},{"port":443,"targetPort":"https","name":"https"}]}}'

echo "=== Phase 10: Deploy Gateways ==="
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
kubectl apply -k "$REPO_ROOT/k8s/gateways/overlays/dev/"
kubectl apply -k "$REPO_ROOT/k8s/gateways/overlays/rec/"

echo "=== Phase 11: Caddy (TLS termination on worker) ==="
$SSH@$WORKER_IP "which caddy >/dev/null 2>&1 || (sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list && sudo apt-get update && sudo apt-get install -y caddy)"

INGRESS_CLUSTER_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.clusterIP}')
$SSH@$WORKER_IP "sudo tee /etc/caddy/Caddyfile > /dev/null << CADDYEOF
dev-gw.gostoa.dev dev-kong.gostoa.dev dev-wm.gostoa.dev rec-gw.gostoa.dev rec-kong.gostoa.dev rec-wm.gostoa.dev {
    reverse_proxy $INGRESS_CLUSTER_IP:80
}
CADDYEOF
sudo systemctl restart caddy"

echo "=== Phase 12: Open K3s API for ArgoCD (OVH nodes) ==="
for ovh_ip in ${OVH_NODE_IPS:?Set OVH_NODE_IPS (space-separated)}; do
  $SSH@$CP_IP "sudo ufw allow from $ovh_ip to any port 6443 comment 'ArgoCD OVH'"
done

echo ""
echo "✅ K3s Gateway Cluster ready!"
echo "  Kubeconfig: $KUBECONFIG_PATH"
echo "  Nodes: $CP_IP (CP) + $WORKER_IP (worker)"
echo "  Namespaces: gateway-dev, gateway-rec"
echo ""
echo "Next steps:"
echo "  1. Create stoa-gateway-secrets (Phase 8 above)"
echo "  2. Create DNS A records → $WORKER_IP:"
echo "     dev-gw, dev-kong, dev-wm, rec-gw, rec-kong, rec-wm (.gostoa.dev)"
echo "  3. Register cluster in ArgoCD (see deploy/k3s-gateways/argocd.yaml)"
