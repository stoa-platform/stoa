#!/bin/bash
# Configure ArgoCD with GitLab repository
set -e

NAMESPACE="argocd"
GITLAB_REPO="https://gitlab.com/cab6961310/stoa-gitops.git"

echo "=== Configuring ArgoCD GitLab Integration ==="

# Check if GITLAB_TOKEN is set
if [ -z "$GITLAB_TOKEN" ]; then
  echo "Error: GITLAB_TOKEN environment variable not set"
  echo "Usage: GITLAB_TOKEN=glpat-xxx ./setup-argocd-gitlab.sh"
  exit 1
fi

# Create GitLab repository secret
echo "Creating GitLab repository secret..."
kubectl create secret generic gitlab-repo-creds \
  --namespace ${NAMESPACE} \
  --from-literal=username=oauth2 \
  --from-literal=password="${GITLAB_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Label the secret for ArgoCD
kubectl label secret gitlab-repo-creds \
  --namespace ${NAMESPACE} \
  argocd.argoproj.io/secret-type=repository \
  --overwrite

# Create repository configuration
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: stoa-gitops-repo
  namespace: ${NAMESPACE}
  labels:
    argocd.argoproj.io/secret-type: repository
stringData:
  type: git
  url: ${GITLAB_REPO}
  username: oauth2
  password: ${GITLAB_TOKEN}
EOF

echo "Repository configured: ${GITLAB_REPO}"

# Apply AppProjects
echo "Applying AppProjects..."
kubectl apply -f /Users/torpedo/stoa/gitops/argocd/projects/stoa-platform.yaml

# Apply ApplicationSets
echo "Applying ApplicationSets..."
kubectl apply -f /Users/torpedo/stoa/gitops/argocd/appsets/

echo ""
echo "=== GitLab Integration Complete ==="
echo ""
echo "ArgoCD is now configured to sync from: ${GITLAB_REPO}"
echo ""
echo "ApplicationSets configured:"
echo "  - tenant-apis: Auto-discovers tenant APIs"
echo "  - environments: Multi-environment deployments"
echo ""
