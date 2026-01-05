#!/bin/bash
# =============================================================================
# Vault Snapshot Backup Script
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# Backs up HashiCorp Vault Raft snapshots to S3 with KMS encryption
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

export BACKUP_COMPONENT="vault"

# Required environment variables
REQUIRED_VARS=(
    "S3_BUCKET"
    "AWS_REGION"
    "VAULT_ADDR"
)

# Optional with defaults
VAULT_NAMESPACE="${VAULT_NAMESPACE:-vault}"
VAULT_POD_SELECTOR="${VAULT_POD_SELECTOR:-app.kubernetes.io/name=vault,vault-active=true}"
VAULT_TOKEN="${VAULT_TOKEN:-}"
KMS_KEY_ID="${KMS_KEY_ID:-}"
BACKUP_RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-7}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

# Derived values
BACKUP_FILENAME="vault-snapshot-${BACKUP_TIMESTAMP}.snap"
S3_PATH="s3://${S3_BUCKET}/vault/${BACKUP_DATE}/${BACKUP_FILENAME}"

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Backup HashiCorp Vault Raft snapshots to S3.

Options:
    -h, --help              Show this help message
    -n, --namespace NAME    Vault namespace (default: vault)
    -d, --dry-run           Dry run - show what would be done
    -v, --verbose           Enable verbose output
    -l, --list              List available backups
    --restore FILE          Restore from backup (S3 path or local file)
    --force                 Force restore without confirmation

Environment Variables:
    S3_BUCKET               S3 bucket for backups (required)
    AWS_REGION              AWS region (required)
    VAULT_ADDR              Vault server address (required)
    VAULT_TOKEN             Vault token for authentication (optional)
    KMS_KEY_ID              KMS key ID for encryption (optional)
    VAULT_NAMESPACE         Vault namespace (default: vault)
    SLACK_WEBHOOK_URL       Slack webhook for notifications (optional)

Examples:
    # Run backup (using Kubernetes service account)
    ./backup-vault.sh

    # Run backup with specific token
    VAULT_TOKEN=hvs.xxx ./backup-vault.sh

    # List existing backups
    ./backup-vault.sh --list

    # Restore from backup
    ./backup-vault.sh --restore s3://bucket/vault/2024-01-15/vault-snapshot.snap
EOF
}

check_vault_status() {
    log_info "Checking Vault status..."

    if ! command -v vault &>/dev/null; then
        log_error "vault CLI is not installed"
        return 1
    fi

    local status
    status=$(vault status -format=json 2>/dev/null || echo '{"sealed": true, "initialized": false}')

    local sealed=$(echo "$status" | jq -r '.sealed')
    local initialized=$(echo "$status" | jq -r '.initialized')

    if [[ "$initialized" != "true" ]]; then
        log_error "Vault is not initialized"
        return 1
    fi

    if [[ "$sealed" == "true" ]]; then
        log_error "Vault is sealed - cannot take snapshot"
        return 1
    fi

    local version=$(echo "$status" | jq -r '.version // "unknown"')
    log_info "Vault status: initialized=$initialized, sealed=$sealed, version=$version"

    return 0
}

get_vault_token() {
    # If token already set, use it
    if [[ -n "${VAULT_TOKEN:-}" ]]; then
        log_debug "Using provided VAULT_TOKEN"
        return 0
    fi

    # Try Kubernetes auth
    log_info "Attempting Kubernetes authentication..."

    local jwt_token
    if [[ -f /var/run/secrets/kubernetes.io/serviceaccount/token ]]; then
        jwt_token=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
    else
        # Running outside cluster - try to get token from secret
        log_info "Getting Vault token from Kubernetes secret..."
        VAULT_TOKEN=$(kubectl get secret -n "$VAULT_NAMESPACE" vault-root-token \
            -o jsonpath='{.data.token}' 2>/dev/null | base64 -d) || true

        if [[ -z "$VAULT_TOKEN" ]]; then
            # Try alternative: vault-init secret
            VAULT_TOKEN=$(kubectl get secret -n "$VAULT_NAMESPACE" vault-init \
                -o jsonpath='{.data.root_token}' 2>/dev/null | base64 -d) || true
        fi

        if [[ -n "$VAULT_TOKEN" ]]; then
            export VAULT_TOKEN
            log_info "Vault token retrieved from Kubernetes secret"
            return 0
        fi

        log_error "Could not retrieve Vault token"
        log_error "Set VAULT_TOKEN environment variable or configure Kubernetes auth"
        return 1
    fi

    # Kubernetes auth login
    local role="${VAULT_K8S_ROLE:-stoa-backup}"
    log_info "Logging in with Kubernetes auth (role: $role)..."

    VAULT_TOKEN=$(vault write -format=json auth/kubernetes/login \
        role="$role" \
        jwt="$jwt_token" | jq -r '.auth.client_token')

    if [[ -z "$VAULT_TOKEN" || "$VAULT_TOKEN" == "null" ]]; then
        log_error "Kubernetes authentication failed"
        return 1
    fi

    export VAULT_TOKEN
    log_info "Kubernetes authentication successful"
}

perform_snapshot() {
    local temp_dir=$1
    local local_snapshot="${temp_dir}/${BACKUP_FILENAME}"
    local start_time=$(date +%s)

    log_info "Creating Vault Raft snapshot..."

    # Take snapshot
    if vault operator raft snapshot save "$local_snapshot"; then
        log_info "Snapshot saved to: $local_snapshot"
    else
        log_error "Failed to create Vault snapshot"
        return 1
    fi

    # Verify snapshot file
    if [[ ! -f "$local_snapshot" ]] || [[ ! -s "$local_snapshot" ]]; then
        log_error "Snapshot file is empty or missing"
        return 1
    fi

    local snapshot_size=$(du -h "$local_snapshot" | cut -f1)
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_info "Snapshot completed: $snapshot_size in $(format_duration $duration)"

    # Verify snapshot integrity
    log_info "Verifying snapshot integrity..."
    if vault operator raft snapshot inspect "$local_snapshot" &>/dev/null; then
        log_info "Snapshot integrity verified"
    else
        log_warn "Could not verify snapshot integrity (may be expected for encrypted snapshots)"
    fi

    echo "$local_snapshot"
}

upload_snapshot() {
    local local_file=$1

    log_info "Uploading snapshot to S3..."
    log_info "  Destination: $S3_PATH"
    log_info "  KMS Key: ${KMS_KEY_ID:-default}"

    upload_to_s3 "$local_file" "$S3_PATH" "$KMS_KEY_ID"
}

verify_snapshot() {
    log_info "Verifying snapshot in S3..."

    local file_info
    file_info=$(aws s3 ls "$S3_PATH" 2>/dev/null)

    if [[ -z "$file_info" ]]; then
        log_error "Snapshot file not found in S3"
        return 1
    fi

    log_info "Snapshot verified: $file_info"
    return 0
}

list_snapshots() {
    log_info "Listing Vault snapshots in S3..."
    echo ""
    echo "Available snapshots (most recent first):"
    echo "=========================================="
    list_s3_backups "s3://${S3_BUCKET}/vault/" 20
    echo ""
}

cleanup_old_snapshots() {
    log_info "Cleaning up old snapshots (keeping last $BACKUP_RETENTION_COUNT)..."
    cleanup_old_s3_backups "s3://${S3_BUCKET}/vault/" "$BACKUP_RETENTION_COUNT"
}

# -----------------------------------------------------------------------------
# Restore Function
# -----------------------------------------------------------------------------

restore_snapshot() {
    local snapshot_path=$1
    local force=${2:-false}
    local temp_dir
    temp_dir=$(create_temp_dir "vault-restore")

    trap "cleanup_temp_dir '$temp_dir'" EXIT

    log_info "Starting Vault snapshot restore..."
    log_warn "This will REPLACE the current Vault data!"
    log_warn "All Vault pods will need to be restarted."

    # Confirm restore
    if [[ "$force" != "true" ]]; then
        read -p "Are you sure you want to proceed? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Restore cancelled"
            return 0
        fi
    fi

    local local_file="${temp_dir}/restore.snap"

    # Download if S3 path
    if [[ "$snapshot_path" == s3://* ]]; then
        download_from_s3 "$snapshot_path" "$local_file"
    else
        cp "$snapshot_path" "$local_file"
    fi

    # Get Vault token
    get_vault_token

    # Verify snapshot before restore
    log_info "Verifying snapshot before restore..."
    if vault operator raft snapshot inspect "$local_file" &>/dev/null; then
        log_info "Snapshot verification passed"
    else
        log_warn "Snapshot verification unclear - proceeding with restore"
    fi

    # Perform restore
    log_info "Restoring Vault from snapshot..."
    if vault operator raft snapshot restore -force "$local_file"; then
        log_info "Snapshot restore command completed"
    else
        log_error "Snapshot restore failed"
        return 1
    fi

    # Restart Vault pods to pick up new data
    log_info "Restarting Vault pods..."
    kubectl rollout restart statefulset/vault -n "$VAULT_NAMESPACE"
    kubectl rollout status statefulset/vault -n "$VAULT_NAMESPACE" --timeout=300s

    log_info "Restore completed successfully"
    send_slack_notification "success" "Vault restored from snapshot" "Source: $snapshot_path"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    local dry_run=false
    local list_only=false
    local restore_path=""
    local force=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -n|--namespace)
                VAULT_NAMESPACE="$2"
                shift 2
                ;;
            -d|--dry-run)
                dry_run=true
                shift
                ;;
            -v|--verbose)
                LOG_LEVEL="DEBUG"
                shift
                ;;
            -l|--list)
                list_only=true
                shift
                ;;
            --restore)
                restore_path="$2"
                shift 2
                ;;
            --force)
                force=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # List mode
    if [[ "$list_only" == "true" ]]; then
        check_required_vars "S3_BUCKET"
        check_aws_credentials
        list_snapshots
        exit 0
    fi

    # Restore mode
    if [[ -n "$restore_path" ]]; then
        check_required_vars "S3_BUCKET" "AWS_REGION" "VAULT_ADDR"
        check_aws_credentials
        check_kubectl
        restore_snapshot "$restore_path" "$force"
        exit 0
    fi

    # Backup mode
    log_info "========================================"
    log_info "Vault Raft Snapshot Backup"
    log_info "========================================"
    log_info "Environment: $ENVIRONMENT"
    log_info "Date: $BACKUP_DATE"
    log_info "Vault Address: $VAULT_ADDR"
    log_info "S3 Bucket: $S3_BUCKET"
    log_info "========================================"

    # Validation
    check_required_vars "${REQUIRED_VARS[@]}"
    check_aws_credentials

    if [[ "$dry_run" == "true" ]]; then
        log_info "[DRY RUN] Would backup to: $S3_PATH"
        exit 0
    fi

    # Get Vault token
    get_vault_token

    # Check Vault status
    check_vault_status

    # Create temp directory
    local temp_dir
    temp_dir=$(create_temp_dir "vault-backup")
    trap "cleanup_temp_dir '$temp_dir'" EXIT

    # Perform snapshot
    local snapshot_file
    snapshot_file=$(perform_snapshot "$temp_dir")

    # Upload to S3
    upload_snapshot "$snapshot_file"

    # Verify
    verify_snapshot

    # Cleanup old snapshots
    cleanup_old_snapshots

    # Success notification
    local snapshot_size=$(du -h "$snapshot_file" | cut -f1)
    send_slack_notification "success" "Vault snapshot backup completed" "Size: $snapshot_size\nPath: $S3_PATH"

    log_info "========================================"
    log_info "Backup completed successfully!"
    log_info "S3 Path: $S3_PATH"
    log_info "========================================"
}

main "$@"
