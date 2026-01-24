#!/bin/bash
# =============================================================================
# Litmus Chaos Engineering Installation Script
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# Installs LitmusChaos for chaos engineering experiments
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
LITMUS_VERSION="${LITMUS_VERSION:-3.0.0}"
LITMUS_NAMESPACE="litmus"
CHAOS_NAMESPACE="stoa-system"

# =============================================================================
# Functions
# =============================================================================

print_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║         STOA Platform - Litmus Chaos Engineering Setup        ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi

    # Check helm
    if ! command -v helm &> /dev/null; then
        log_error "helm is not installed"
        exit 1
    fi

    # Check cluster access
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi

    log_success "Prerequisites checked"
}

install_litmus() {
    log_info "Installing Litmus ChaosCenter..."

    # Add Litmus Helm repo
    helm repo add litmuschaos https://litmuschaos.github.io/litmus-helm/
    helm repo update

    # Create namespace
    kubectl create namespace "$LITMUS_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Install Litmus
    helm upgrade --install chaos litmuschaos/litmus \
        --namespace "$LITMUS_NAMESPACE" \
        --version "$LITMUS_VERSION" \
        --set portal.frontend.service.type=ClusterIP \
        --set portal.server.service.type=ClusterIP \
        --set mongodb.auth.enabled=true \
        --set mongodb.auth.rootPassword="litmus-chaos-db" \
        --wait \
        --timeout 10m

    log_success "Litmus ChaosCenter installed"
}

install_chaos_operator() {
    log_info "Installing Chaos Operator in target namespace..."

    # Create namespace if not exists
    kubectl create namespace "$CHAOS_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Apply CRDs
    kubectl apply -f https://raw.githubusercontent.com/litmuschaos/litmus/master/chaosHub/charts/chaosexperiment/crds/chaosengine-crd.yaml
    kubectl apply -f https://raw.githubusercontent.com/litmuschaos/litmus/master/chaosHub/charts/chaosexperiment/crds/chaosexperiment-crd.yaml
    kubectl apply -f https://raw.githubusercontent.com/litmuschaos/litmus/master/chaosHub/charts/chaosexperiment/crds/chaosresult-crd.yaml

    # Install RBAC for chaos runner
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: litmus-admin
  namespace: $CHAOS_NAMESPACE
  labels:
    app.kubernetes.io/name: litmus
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: litmus-admin
  labels:
    app.kubernetes.io/name: litmus
rules:
  - apiGroups: [""]
    resources: ["pods", "events", "configmaps", "secrets", "services"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["pods/log", "pods/exec"]
    verbs: ["get", "list", "watch", "create"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "list", "watch", "create", "delete"]
  - apiGroups: ["litmuschaos.io"]
    resources: ["*"]
    verbs: ["*"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: litmus-admin
  labels:
    app.kubernetes.io/name: litmus
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: litmus-admin
subjects:
  - kind: ServiceAccount
    name: litmus-admin
    namespace: $CHAOS_NAMESPACE
EOF

    log_success "Chaos Operator RBAC configured"
}

install_experiments() {
    log_info "Installing chaos experiments..."

    # Generic experiments
    kubectl apply -f https://hub.litmuschaos.io/api/chaos/master?file=faults/kubernetes/pod-delete/fault.yaml -n "$CHAOS_NAMESPACE"
    kubectl apply -f https://hub.litmuschaos.io/api/chaos/master?file=faults/kubernetes/pod-cpu-hog/fault.yaml -n "$CHAOS_NAMESPACE"
    kubectl apply -f https://hub.litmuschaos.io/api/chaos/master?file=faults/kubernetes/pod-memory-hog/fault.yaml -n "$CHAOS_NAMESPACE"
    kubectl apply -f https://hub.litmuschaos.io/api/chaos/master?file=faults/kubernetes/pod-network-latency/fault.yaml -n "$CHAOS_NAMESPACE"
    kubectl apply -f https://hub.litmuschaos.io/api/chaos/master?file=faults/kubernetes/pod-network-loss/fault.yaml -n "$CHAOS_NAMESPACE"

    log_success "Chaos experiments installed"
}

apply_custom_experiments() {
    log_info "Applying custom STOA experiments..."

    local experiments_dir="$PROJECT_ROOT/tests/chaos/experiments"

    if [[ -d "$experiments_dir" ]]; then
        for exp in "$experiments_dir"/*.yaml; do
            if [[ -f "$exp" ]]; then
                log_info "Applying: $(basename "$exp")"
                kubectl apply -f "$exp" -n "$CHAOS_NAMESPACE"
            fi
        done
    fi

    log_success "Custom experiments applied"
}

verify_installation() {
    log_info "Verifying installation..."

    echo ""
    echo "Litmus ChaosCenter pods:"
    kubectl get pods -n "$LITMUS_NAMESPACE"

    echo ""
    echo "Chaos experiments available:"
    kubectl get chaosexperiments -n "$CHAOS_NAMESPACE"

    echo ""
    echo "Chaos engines (running):"
    kubectl get chaosengines -n "$CHAOS_NAMESPACE"

    log_success "Installation verified"
}

print_access_info() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "                    Litmus ChaosCenter Access"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "To access the ChaosCenter UI, run:"
    echo ""
    echo "  kubectl port-forward svc/chaos-litmus-frontend-service 9091:9091 -n $LITMUS_NAMESPACE"
    echo ""
    echo "Then open: http://localhost:9091"
    echo ""
    echo "Default credentials:"
    echo "  Username: admin"
    echo "  Password: litmus"
    echo ""
    echo "To run a chaos experiment:"
    echo ""
    echo "  kubectl apply -f tests/chaos/experiments/pod-delete-api.yaml"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
}

uninstall() {
    log_warn "Uninstalling Litmus..."

    helm uninstall chaos -n "$LITMUS_NAMESPACE" || true
    kubectl delete namespace "$LITMUS_NAMESPACE" --ignore-not-found

    log_success "Litmus uninstalled"
}

# =============================================================================
# Main
# =============================================================================

main() {
    print_banner

    local action="${1:-install}"

    case "$action" in
        install)
            check_prerequisites
            install_litmus
            install_chaos_operator
            install_experiments
            apply_custom_experiments
            verify_installation
            print_access_info
            ;;
        uninstall)
            uninstall
            ;;
        verify)
            verify_installation
            ;;
        *)
            echo "Usage: $0 [install|uninstall|verify]"
            exit 1
            ;;
    esac
}

main "$@"
