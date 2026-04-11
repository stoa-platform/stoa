#!/bin/bash
# =============================================================================
# STOA Vault Local Setup — One-Command Bootstrap
# =============================================================================
# Deploys HashiCorp Vault on local K3s via Helm, then bootstraps all engines:
#   KV v2, PKI, Transit, Database, TOTP, AppRole auth
#
# Prerequisites:
#   - K3s / Docker Desktop Kubernetes running
#   - helm, kubectl, jq in PATH
#   - Docker Compose services running (PostgreSQL, Keycloak)
#
# Usage:
#   ./deploy/local/vault/setup-vault-local.sh          # Full setup
#   ./deploy/local/vault/setup-vault-local.sh --teardown  # Remove Vault
#   ./deploy/local/vault/setup-vault-local.sh --status    # Check status
#
# Architecture:
#   Vault server runs on K3s (namespace: vault)
#   Vault Agent runs on Docker Compose (profile: vault)
#   Both managed via GitOps — all config in this directory
# =============================================================================

set -euo pipefail

# ⚠️ LOCAL DEV ONLY — this script wires a dev-mode Vault with a well-known
# root token. Never run against a non-local kube context.
CURRENT_CONTEXT="$(kubectl config current-context 2>/dev/null || echo '')"
case "$CURRENT_CONTEXT" in
  k3d-*|kind-*|docker-desktop|minikube|rancher-desktop|'')
    ;;
  *)
    echo "refusing to run against kube context '$CURRENT_CONTEXT' — this script is for local dev clusters only" >&2
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_NAMESPACE="vault"
VAULT_RELEASE="vault"
# Dev root token, hardcoded intentionally — Vault runs in -dev mode locally.
VAULT_TOKEN="stoa-dev-root-token"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[vault-setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[vault-setup]${NC} $*"; }
err()  { echo -e "${RED}[vault-setup]${NC} $*" >&2; }

# ==========================================================================
# Prerequisites Check
# ==========================================================================
check_prerequisites() {
  log "Checking prerequisites..."
  local missing=0

  for cmd in helm kubectl jq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      err "Missing: $cmd"
      missing=1
    fi
  done

  if ! kubectl cluster-info >/dev/null 2>&1; then
    err "K3s / Kubernetes not reachable"
    missing=1
  fi

  if [ "$missing" -eq 1 ]; then
    err "Prerequisites check failed. Install missing tools and ensure K3s is running."
    exit 1
  fi

  log "Prerequisites OK"
}

# ==========================================================================
# Phase 1: Deploy Vault Helm Chart
# ==========================================================================
deploy_vault() {
  log "=== Deploying Vault on K3s ==="

  # Add Helm repo
  helm repo add hashicorp https://helm.releases.hashicorp.com 2>/dev/null || true
  helm repo update >/dev/null 2>&1

  # Create namespace
  kubectl create namespace "$VAULT_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

  # Deploy Vault
  helm upgrade --install "$VAULT_RELEASE" hashicorp/vault \
    --namespace "$VAULT_NAMESPACE" \
    -f "${SCRIPT_DIR}/values-local.yaml" \
    --wait \
    --timeout 120s

  log "Vault Helm chart deployed"

  # Wait for pod ready
  kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=vault \
    -n "$VAULT_NAMESPACE" \
    --timeout=120s

  log "Vault pod ready"
}

# ==========================================================================
# Phase 2: Bootstrap via Init Job
# ==========================================================================
bootstrap_vault() {
  log "=== Bootstrapping Vault ==="

  # Create ConfigMap from init script (source of truth is the .sh file)
  kubectl create configmap vault-init-script \
    --from-file=init-vault-local.sh="${SCRIPT_DIR}/init-vault-local.sh" \
    -n "$VAULT_NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -
  log "Created ConfigMap: vault-init-script"

  # Create policies ConfigMap (if policies dir has HCL files)
  if ls "${SCRIPT_DIR}/policies/"*.hcl >/dev/null 2>&1; then
    kubectl create configmap vault-policies \
      --from-file="${SCRIPT_DIR}/policies/" \
      -n "$VAULT_NAMESPACE" \
      --dry-run=client -o yaml | kubectl apply -f -
    log "Created ConfigMap: vault-policies"
  else
    warn "No policies found in ${SCRIPT_DIR}/policies/ (Phase 2 not yet implemented)"
  fi

  # Apply RBAC + Job
  kubectl delete job vault-init -n "$VAULT_NAMESPACE" --ignore-not-found 2>/dev/null
  kubectl apply -f "${SCRIPT_DIR}/vault-init-job.yaml"

  # Wait for completion
  log "Waiting for vault-init Job to complete..."
  if kubectl wait --for=condition=complete job/vault-init \
    -n "$VAULT_NAMESPACE" --timeout=180s; then
    log "Bootstrap complete"
  else
    err "Bootstrap Job failed. Check logs:"
    err "  kubectl logs job/vault-init -n $VAULT_NAMESPACE"
    exit 1
  fi
}

# ==========================================================================
# Verification
# ==========================================================================
verify_vault() {
  log "=== Verifying Vault ==="

  # Port-forward in background
  kubectl port-forward -n "$VAULT_NAMESPACE" svc/vault 8200:8200 &
  PF_PID=$!
  sleep 3

  # Health check
  if curl -sf http://localhost:8200/v1/sys/health | jq . >/dev/null 2>&1; then
    log "Health check: OK"
  else
    err "Health check: FAILED"
    kill "$PF_PID" 2>/dev/null
    exit 1
  fi

  # Engines check
  log "Enabled engines:"
  curl -sf -H "X-Vault-Token:$VAULT_TOKEN" \
    http://localhost:8200/v1/sys/mounts | jq -r 'keys[]' | sort

  # KV check
  if curl -sf -H "X-Vault-Token:$VAULT_TOKEN" \
    http://localhost:8200/v1/stoa/data/k8s/gateway | jq -r '.data.data' >/dev/null 2>&1; then
    log "KV seed check: OK (stoa/k8s/gateway readable)"
  else
    warn "KV seed check: WARN (stoa/k8s/gateway not readable)"
  fi

  # E2E personas check
  if curl -sf -H "X-Vault-Token:$VAULT_TOKEN" \
    http://localhost:8200/v1/stoa/data/dev/e2e-personas | jq -r '.data.data | keys | length' | grep -q 7; then
    log "E2E personas check: OK (7 personas)"
  else
    warn "E2E personas check: WARN"
  fi

  # Cleanup port-forward
  kill "$PF_PID" 2>/dev/null || true

  log ""
  log "========================================"
  log "  Vault local setup complete"
  log "========================================"
  log ""
  log "Access:"
  log "  K3s pods:  http://vault.vault.svc.cluster.local:8200"
  log "  Docker:    kubectl port-forward -n vault svc/vault 8200:8200"
  log "  Ingress:   http://vault.stoa.local (after ingress update)"
  log "  UI:        http://localhost:8200/ui (via port-forward)"
  log "  Token:     $VAULT_TOKEN"
  log ""
  log "Init Job logs:"
  log "  kubectl logs job/vault-init -n vault"
}

# ==========================================================================
# Teardown
# ==========================================================================
teardown_vault() {
  warn "=== Tearing down Vault ==="

  helm uninstall "$VAULT_RELEASE" -n "$VAULT_NAMESPACE" 2>/dev/null || true
  kubectl delete job vault-init -n "$VAULT_NAMESPACE" --ignore-not-found
  kubectl delete configmap vault-init-script vault-policies -n "$VAULT_NAMESPACE" --ignore-not-found
  kubectl delete serviceaccount vault-init -n "$VAULT_NAMESPACE" --ignore-not-found
  kubectl delete clusterrole vault-init-secrets-manager --ignore-not-found
  kubectl delete clusterrolebinding vault-init-secrets-manager --ignore-not-found

  # Keep namespace and PVCs for data preservation
  warn "Namespace '$VAULT_NAMESPACE' and PVCs preserved. To fully remove:"
  warn "  kubectl delete namespace $VAULT_NAMESPACE"

  log "Teardown complete"
}

# ==========================================================================
# Status
# ==========================================================================
status_vault() {
  log "=== Vault Status ==="

  echo ""
  echo "Helm release:"
  helm list -n "$VAULT_NAMESPACE" 2>/dev/null || echo "  Not deployed"

  echo ""
  echo "Pods:"
  kubectl get pods -n "$VAULT_NAMESPACE" 2>/dev/null || echo "  No pods"

  echo ""
  echo "Init Job:"
  kubectl get job vault-init -n "$VAULT_NAMESPACE" 2>/dev/null || echo "  No init job"

  echo ""
  echo "Services:"
  kubectl get svc -n "$VAULT_NAMESPACE" 2>/dev/null || echo "  No services"
}

# ==========================================================================
# Main
# ==========================================================================
case "${1:-}" in
  --teardown)
    teardown_vault
    ;;
  --status)
    status_vault
    ;;
  *)
    check_prerequisites
    deploy_vault
    bootstrap_vault
    verify_vault
    ;;
esac
