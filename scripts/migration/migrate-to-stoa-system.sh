#!/bin/bash
# =============================================================================
# Migration Script: apim-system -> stoa-system
# =============================================================================
# STOA Platform - CAB-250
# Migrates all resources from apim-system namespace to stoa-system
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXPORT_DIR="/tmp/stoa-migration"
SOURCE_NS="apim-system"
TARGET_NS="stoa-system"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create export directory
mkdir -p "$EXPORT_DIR"

# Helper function to clean YAML metadata using yq (if available) or grep
clean_yaml() {
    # Use yq if available for proper YAML processing
    if command -v yq &>/dev/null; then
        yq 'del(.metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .metadata.generation, .metadata.selfLink, .metadata.managedFields, .metadata.ownerReferences, .status)'
    else
        # Fallback: simple grep to remove problematic lines
        grep -v -E '^\s*(resourceVersion:|uid:|creationTimestamp:|generation:|selfLink:)' | \
        grep -v -E '^\s*managedFields:' | \
        grep -v -E '^\s*ownerReferences:'
    fi
}

# =============================================================================
# Step 1: Ensure target namespace exists
# =============================================================================
ensure_namespace() {
    log_info "Ensuring namespace $TARGET_NS exists..."
    kubectl create namespace "$TARGET_NS" --dry-run=client -o yaml | kubectl apply -f -
}

# =============================================================================
# Step 2: Export and migrate secrets
# =============================================================================
migrate_secrets() {
    log_info "Migrating secrets from $SOURCE_NS to $TARGET_NS..."

    # List of secrets to migrate (exclude default service account tokens and Helm secrets)
    SECRETS=(
        "api-tls"
        "apigateway-runtime-stoa-tls"
        "auth-tls"
        "awx-admin-password"
        "awx-postgres-configuration"
        "awx-tls"
        "console-tls"
        "control-plane-api-secrets"
        "ecr-secret"
        "gitlab-secrets"
        "keycloak-admin-secret"
        "keycloak-db-secret"
        "mcp-gateway-tls"
        "mcp-gateway-secrets"
    )

    for secret in "${SECRETS[@]}"; do
        if kubectl get secret "$secret" -n "$SOURCE_NS" &>/dev/null; then
            log_info "  Migrating secret: $secret"
            kubectl get secret "$secret" -n "$SOURCE_NS" -o yaml | \
                sed "s/namespace: $SOURCE_NS/namespace: $TARGET_NS/g" | \
                clean_yaml | \
                kubectl apply -f - -n "$TARGET_NS" 2>/dev/null || log_warn "    Failed to migrate: $secret"
        else
            log_warn "  Secret not found: $secret"
        fi
    done
}

# =============================================================================
# Step 3: Export and migrate configmaps (skip AWX ones with owner references)
# =============================================================================
migrate_configmaps() {
    log_info "Migrating configmaps from $SOURCE_NS to $TARGET_NS..."

    CONFIGMAPS=(
        "control-plane-ui-config"
        "keycloak-realm"
        "redpanda"
        "redpanda-console"
    )

    for cm in "${CONFIGMAPS[@]}"; do
        if kubectl get configmap "$cm" -n "$SOURCE_NS" &>/dev/null; then
            log_info "  Migrating configmap: $cm"
            kubectl get configmap "$cm" -n "$SOURCE_NS" -o yaml | \
                sed "s/namespace: $SOURCE_NS/namespace: $TARGET_NS/g" | \
                clean_yaml | \
                kubectl apply -f - -n "$TARGET_NS" 2>/dev/null || log_warn "    Failed to migrate: $cm"
        else
            log_warn "  ConfigMap not found: $cm"
        fi
    done
}

# =============================================================================
# Step 4: Export and migrate deployments with updated DNS references
# =============================================================================
migrate_deployments() {
    log_info "Exporting deployments with updated internal DNS references..."

    DEPLOYMENTS=(
        "control-plane-api"
        "control-plane-ui"
        "mcp-gateway"
        "keycloak"
        "apigateway"
        "devportal"
        "awx-web"
        "awx-task"
        "awx-operator-controller-manager"
        "redpanda-console"
    )

    for deploy in "${DEPLOYMENTS[@]}"; do
        if kubectl get deployment "$deploy" -n "$SOURCE_NS" &>/dev/null; then
            log_info "  Exporting deployment: $deploy"
            kubectl get deployment "$deploy" -n "$SOURCE_NS" -o yaml | \
                sed "s/namespace: $SOURCE_NS/namespace: $TARGET_NS/g" | \
                sed "s/$SOURCE_NS\.svc\.cluster\.local/$TARGET_NS.svc.cluster.local/g" | \
                sed "s/redpanda\.$SOURCE_NS/redpanda.$TARGET_NS/g" | \
                sed "s/awx-service\.$SOURCE_NS/awx-service.$TARGET_NS/g" | \
                sed "s/awx\.$SOURCE_NS/awx.$TARGET_NS/g" | \
                clean_yaml > "$EXPORT_DIR/deploy-$deploy.yaml"
        else
            log_warn "  Deployment not found: $deploy"
        fi
    done
}

# =============================================================================
# Step 5: Export and migrate services
# =============================================================================
migrate_services() {
    log_info "Exporting services..."

    SERVICES=(
        "control-plane-api"
        "control-plane-ui"
        "mcp-gateway"
        "keycloak"
        "apigateway"
        "apigateway-runtime"
        "devportal"
        "awx-service"
        "awx-postgres"
        "redpanda"
        "redpanda-console"
    )

    for svc in "${SERVICES[@]}"; do
        if kubectl get service "$svc" -n "$SOURCE_NS" &>/dev/null; then
            log_info "  Exporting service: $svc"
            kubectl get service "$svc" -n "$SOURCE_NS" -o yaml | \
                yq 'del(.metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .metadata.generation, .metadata.selfLink, .metadata.managedFields, .metadata.ownerReferences, .status, .spec.clusterIP, .spec.clusterIPs)' | \
                sed "s/namespace: $SOURCE_NS/namespace: $TARGET_NS/g" > "$EXPORT_DIR/svc-$svc.yaml"
        else
            log_warn "  Service not found: $svc"
        fi
    done
}

# =============================================================================
# Step 6: Export and migrate statefulsets
# =============================================================================
migrate_statefulsets() {
    log_info "Exporting statefulsets..."

    STATEFULSETS=(
        "elasticsearch-master"
        "redpanda"
    )

    for sts in "${STATEFULSETS[@]}"; do
        if kubectl get statefulset "$sts" -n "$SOURCE_NS" &>/dev/null; then
            log_info "  Exporting statefulset: $sts"
            kubectl get statefulset "$sts" -n "$SOURCE_NS" -o yaml | \
                sed "s/namespace: $SOURCE_NS/namespace: $TARGET_NS/g" | \
                sed "s/$SOURCE_NS\.svc\.cluster\.local/$TARGET_NS.svc.cluster.local/g" | \
                clean_yaml > "$EXPORT_DIR/sts-$sts.yaml"
        else
            log_warn "  StatefulSet not found: $sts"
        fi
    done
}

# =============================================================================
# Step 7: Export and migrate ingresses
# =============================================================================
migrate_ingresses() {
    log_info "Exporting ingresses..."

    INGRESSES=(
        "apigateway"
        "apigateway-runtime-stoa"
        "awx-ingress"
        "control-plane-api"
        "control-plane-ui"
        "keycloak"
        "mcp-gateway"
    )

    for ing in "${INGRESSES[@]}"; do
        if kubectl get ingress "$ing" -n "$SOURCE_NS" &>/dev/null; then
            log_info "  Exporting ingress: $ing"
            kubectl get ingress "$ing" -n "$SOURCE_NS" -o yaml | \
                sed "s/namespace: $SOURCE_NS/namespace: $TARGET_NS/g" | \
                clean_yaml > "$EXPORT_DIR/ing-$ing.yaml"
        else
            log_warn "  Ingress not found: $ing"
        fi
    done
}

# =============================================================================
# Step 8: Export HPAs
# =============================================================================
migrate_hpas() {
    log_info "Exporting HPAs..."

    kubectl get hpa -n "$SOURCE_NS" -o yaml 2>/dev/null | \
        sed "s/namespace: $SOURCE_NS/namespace: $TARGET_NS/g" | \
        clean_yaml > "$EXPORT_DIR/hpas.yaml" || log_warn "No HPAs found"
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo "=============================================="
    echo "STOA Platform Migration: $SOURCE_NS -> $TARGET_NS"
    echo "=============================================="
    echo ""

    case "${1:-export}" in
        export)
            log_info "Phase 1: Exporting resources..."
            ensure_namespace
            migrate_secrets
            migrate_configmaps
            migrate_deployments
            migrate_services
            migrate_statefulsets
            migrate_ingresses
            migrate_hpas

            log_info ""
            log_info "Export complete! Resources saved to: $EXPORT_DIR"
            log_info ""
            log_info "Review the exported files, then run:"
            log_info "  $0 apply"
            ;;

        apply)
            log_info "Phase 2: Applying resources to $TARGET_NS..."

            # Apply in order
            log_info "Applying secrets..."
            # Secrets are already applied during export

            log_info "Applying services..."
            for f in "$EXPORT_DIR"/svc-*.yaml; do
                [ -f "$f" ] && kubectl apply -f "$f" -n "$TARGET_NS" 2>/dev/null || true
            done

            log_info "Applying deployments..."
            for f in "$EXPORT_DIR"/deploy-*.yaml; do
                [ -f "$f" ] && kubectl apply -f "$f" -n "$TARGET_NS" 2>/dev/null || true
            done

            log_info "Applying statefulsets..."
            for f in "$EXPORT_DIR"/sts-*.yaml; do
                [ -f "$f" ] && kubectl apply -f "$f" -n "$TARGET_NS" 2>/dev/null || true
            done

            log_info "Applying ingresses..."
            for f in "$EXPORT_DIR"/ing-*.yaml; do
                [ -f "$f" ] && kubectl apply -f "$f" -n "$TARGET_NS" 2>/dev/null || true
            done

            log_info "Applying HPAs..."
            [ -f "$EXPORT_DIR/hpas.yaml" ] && kubectl apply -f "$EXPORT_DIR/hpas.yaml" -n "$TARGET_NS" 2>/dev/null || true

            log_info ""
            log_info "Apply complete! Verify with:"
            log_info "  kubectl get pods -n $TARGET_NS"
            ;;

        verify)
            log_info "Verifying migration..."
            echo ""
            echo "Pods in $TARGET_NS:"
            kubectl get pods -n "$TARGET_NS"
            echo ""
            echo "Services in $TARGET_NS:"
            kubectl get svc -n "$TARGET_NS"
            echo ""
            echo "Ingresses in $TARGET_NS:"
            kubectl get ingress -n "$TARGET_NS"
            ;;

        cleanup)
            log_warn "This will delete the $SOURCE_NS namespace!"
            read -p "Are you sure? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                log_info "Deleting namespace $SOURCE_NS..."
                kubectl delete namespace "$SOURCE_NS"
                log_info "Cleanup complete!"
            else
                log_info "Cleanup cancelled."
            fi
            ;;

        *)
            echo "Usage: $0 {export|apply|verify|cleanup}"
            echo ""
            echo "  export  - Export resources from $SOURCE_NS (default)"
            echo "  apply   - Apply exported resources to $TARGET_NS"
            echo "  verify  - Verify resources in $TARGET_NS"
            echo "  cleanup - Delete $SOURCE_NS namespace (after verification)"
            exit 1
            ;;
    esac
}

main "$@"
