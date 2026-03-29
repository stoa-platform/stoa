#!/bin/bash
# Configure ArgoCD with Git repository (GitLab or GitHub)
# Supports GIT_PROVIDER=gitlab (default) or GIT_PROVIDER=github
set -e

NAMESPACE="argocd"
GIT_PROVIDER="${GIT_PROVIDER:-gitlab}"

echo "=== Configuring ArgoCD Git Integration (provider: ${GIT_PROVIDER}) ==="

if [ "$GIT_PROVIDER" = "github" ]; then
  # GitHub configuration
  GITHUB_ORG="${GITHUB_ORG:-stoa-platform}"
  GITHUB_GITOPS_REPO="${GITHUB_GITOPS_REPO:-stoa-gitops}"
  GIT_REPO="https://github.com/${GITHUB_ORG}/${GITHUB_GITOPS_REPO}.git"

  if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable not set"
    echo "Usage: GIT_PROVIDER=github GITHUB_TOKEN=ghp_xxx ./setup-argocd-git.sh"
    exit 1
  fi

  GIT_USERNAME="x-access-token"
  GIT_PASSWORD="${GITHUB_TOKEN}"
  SECRET_NAME="github-repo-creds"
else
  # GitLab configuration (default)
  GIT_REPO="https://gitlab.com/cab6961310/stoa-gitops.git"

  if [ -z "$GITLAB_TOKEN" ]; then
    echo "Error: GITLAB_TOKEN environment variable not set"
    echo "Usage: GITLAB_TOKEN=glpat-xxx ./setup-argocd-git.sh"
    exit 1
  fi

  GIT_USERNAME="oauth2"
  GIT_PASSWORD="${GITLAB_TOKEN}"
  SECRET_NAME="gitlab-repo-creds"
fi

# Create repository secret
echo "Creating ${GIT_PROVIDER} repository secret..."
kubectl create secret generic "${SECRET_NAME}" \
  --namespace ${NAMESPACE} \
  --from-literal=username="${GIT_USERNAME}" \
  --from-literal=password="${GIT_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Label the secret for ArgoCD
kubectl label secret "${SECRET_NAME}" \
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
  url: ${GIT_REPO}
  username: ${GIT_USERNAME}
  password: ${GIT_PASSWORD}
EOF

echo "Repository configured: ${GIT_REPO}"

# Apply AppProjects
echo "Applying AppProjects..."
kubectl apply -f /Users/torpedo/stoa/gitops/argocd/projects/stoa-platform.yaml

# Apply ApplicationSets
echo "Applying ApplicationSets..."
kubectl apply -f /Users/torpedo/stoa/gitops/argocd/appsets/

echo ""
echo "=== Git Integration Complete ==="
echo ""
echo "ArgoCD is now configured to sync from: ${GIT_REPO}"
echo ""
echo "ApplicationSets configured:"
echo "  - tenant-apis: Auto-discovers tenant APIs"
echo "  - environments: Multi-environment deployments"
echo ""
