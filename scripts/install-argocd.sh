#!/bin/bash
# Install ArgoCD on EKS for APIM Platform GitOps
set -e

NAMESPACE="argocd"
ARGOCD_VERSION="5.51.6"
DOMAIN="argocd.apim.cab-i.com"

echo "=== Installing ArgoCD for APIM Platform ==="

# Create namespace
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Add Argo Helm repo
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

# Install ArgoCD with custom values
echo "Installing ArgoCD ${ARGOCD_VERSION}..."
helm upgrade --install argocd argo/argo-cd \
  --namespace ${NAMESPACE} \
  --version ${ARGOCD_VERSION} \
  --set server.ingress.enabled=true \
  --set server.ingress.ingressClassName=nginx \
  --set "server.ingress.hosts[0]=${DOMAIN}" \
  --set "server.ingress.tls[0].secretName=argocd-tls" \
  --set "server.ingress.tls[0].hosts[0]=${DOMAIN}" \
  --set "server.ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt-prod" \
  --set "server.ingress.annotations.nginx\.ingress\.kubernetes\.io/ssl-passthrough=true" \
  --set "server.ingress.annotations.nginx\.ingress\.kubernetes\.io/backend-protocol=HTTPS" \
  --set configs.params."server\.insecure"=true \
  --set applicationSet.enabled=true \
  --set notifications.enabled=true \
  --wait

# Wait for ArgoCD to be ready
echo "Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n ${NAMESPACE}

# Get initial admin password
echo ""
echo "=== ArgoCD Installation Complete ==="
echo "URL: https://${DOMAIN}"
echo ""
echo "Initial admin password:"
kubectl -n ${NAMESPACE} get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
echo ""
echo ""
echo "To login via CLI:"
echo "  argocd login ${DOMAIN} --username admin --password <password>"
echo ""
echo "Next steps:"
echo "1. Change admin password"
echo "2. Configure GitLab repository credentials"
echo "3. Apply AppProjects and ApplicationSets"
echo ""
