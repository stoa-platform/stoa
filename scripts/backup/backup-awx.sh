#!/bin/bash
# =============================================================================
# AWX Database Backup Script
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# Backs up AWX PostgreSQL database to S3 with KMS encryption
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

export BACKUP_COMPONENT="awx"

# Required environment variables
REQUIRED_VARS=(
    "S3_BUCKET"
    "AWS_REGION"
)

# Optional with defaults
AWX_NAMESPACE="${AWX_NAMESPACE:-awx}"
AWX_POSTGRES_SELECTOR="${AWX_POSTGRES_SELECTOR:-app.kubernetes.io/component=database}"
AWX_DB_NAME="${AWX_DB_NAME:-awx}"
AWX_DB_USER="${AWX_DB_USER:-awx}"
KMS_KEY_ID="${KMS_KEY_ID:-}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

# Derived values
BACKUP_FILENAME="awx-backup-${BACKUP_TIMESTAMP}.sql.gz"
S3_PATH="s3://${S3_BUCKET}/awx/${BACKUP_DATE}/${BACKUP_FILENAME}"

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Backup AWX PostgreSQL database to S3.

Options:
    -h, --help              Show this help message
    -n, --namespace NAME    AWX namespace (default: awx)
    -d, --dry-run           Dry run - show what would be done
    -v, --verbose           Enable verbose output
    -l, --list              List available backups
    --restore FILE          Restore from backup (S3 path or local file)

Environment Variables:
    S3_BUCKET               S3 bucket for backups (required)
    AWS_REGION              AWS region (required)
    KMS_KEY_ID              KMS key ID for encryption (optional)
    AWX_NAMESPACE           AWX namespace (default: awx)
    AWX_DB_NAME             Database name (default: awx)
    AWX_DB_USER             Database user (default: awx)
    SLACK_WEBHOOK_URL       Slack webhook for notifications (optional)

Examples:
    # Run backup
    ./backup-awx.sh

    # Dry run
    ./backup-awx.sh --dry-run

    # List existing backups
    ./backup-awx.sh --list

    # Restore from backup
    ./backup-awx.sh --restore s3://bucket/awx/2024-01-15/awx-backup.sql.gz
EOF
}

find_postgres_pod() {
    log_info "Finding AWX PostgreSQL pod in namespace: $AWX_NAMESPACE"

    local pod_name
    pod_name=$(get_pod_name "$AWX_NAMESPACE" "$AWX_POSTGRES_SELECTOR")

    if [[ -z "$pod_name" ]]; then
        log_error "Could not find AWX PostgreSQL pod with selector: $AWX_POSTGRES_SELECTOR"
        return 1
    fi

    log_info "Found PostgreSQL pod: $pod_name"
    echo "$pod_name"
}

get_db_password() {
    log_info "Retrieving database password from secret..."

    local password
    password=$(kubectl get secret -n "$AWX_NAMESPACE" awx-postgres-configuration \
        -o jsonpath='{.data.password}' 2>/dev/null | base64 -d)

    if [[ -z "$password" ]]; then
        # Try alternative secret name
        password=$(kubectl get secret -n "$AWX_NAMESPACE" awx-postgres \
            -o jsonpath='{.data.password}' 2>/dev/null | base64 -d)
    fi

    if [[ -z "$password" ]]; then
        log_error "Could not retrieve PostgreSQL password"
        return 1
    fi

    echo "$password"
}

perform_backup() {
    local postgres_pod=$1
    local temp_dir=$2

    local local_backup="${temp_dir}/${BACKUP_FILENAME}"
    local start_time=$(date +%s)

    log_info "Starting PostgreSQL backup..."
    log_info "  Database: $AWX_DB_NAME"
    log_info "  User: $AWX_DB_USER"
    log_info "  Output: $local_backup"

    # Get password
    local db_password
    db_password=$(get_db_password)

    # Perform pg_dump inside the pod
    log_info "Running pg_dump in pod $postgres_pod..."

    kubectl exec -n "$AWX_NAMESPACE" "$postgres_pod" -- \
        pg_dump -U "$AWX_DB_USER" -d "$AWX_DB_NAME" \
        --format=custom \
        --verbose \
        --file=/tmp/awx-backup.dump 2>&1 | while read -r line; do
            log_debug "pg_dump: $line"
        done

    # Compress and copy out of pod
    log_info "Extracting backup from pod..."
    kubectl exec -n "$AWX_NAMESPACE" "$postgres_pod" -- \
        cat /tmp/awx-backup.dump | gzip > "$local_backup"

    # Cleanup inside pod
    kubectl exec -n "$AWX_NAMESPACE" "$postgres_pod" -- \
        rm -f /tmp/awx-backup.dump

    # Verify backup file
    if [[ ! -f "$local_backup" ]] || [[ ! -s "$local_backup" ]]; then
        log_error "Backup file is empty or missing"
        return 1
    fi

    local backup_size=$(du -h "$local_backup" | cut -f1)
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_info "Backup completed: $backup_size in $(format_duration $duration)"

    echo "$local_backup"
}

upload_backup() {
    local local_file=$1

    log_info "Uploading backup to S3..."
    log_info "  Destination: $S3_PATH"
    log_info "  KMS Key: ${KMS_KEY_ID:-default}"

    upload_to_s3 "$local_file" "$S3_PATH" "$KMS_KEY_ID"
}

verify_backup() {
    log_info "Verifying backup in S3..."

    local file_info
    file_info=$(aws s3 ls "$S3_PATH" 2>/dev/null)

    if [[ -z "$file_info" ]]; then
        log_error "Backup file not found in S3"
        return 1
    fi

    log_info "Backup verified: $file_info"
    return 0
}

list_backups() {
    log_info "Listing AWX backups in S3..."
    echo ""
    echo "Available backups (most recent first):"
    echo "========================================"
    list_s3_backups "s3://${S3_BUCKET}/awx/" 20
    echo ""
}

# -----------------------------------------------------------------------------
# Restore Function
# -----------------------------------------------------------------------------

restore_backup() {
    local backup_path=$1
    local temp_dir
    temp_dir=$(create_temp_dir "awx-restore")

    trap "cleanup_temp_dir '$temp_dir'" EXIT

    log_info "Starting AWX database restore..."
    log_warn "This will OVERWRITE the current AWX database!"

    # Confirm restore
    if [[ "${RESTORE_CONFIRM:-false}" != "true" ]]; then
        read -p "Are you sure you want to proceed? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Restore cancelled"
            return 0
        fi
    fi

    local local_file="${temp_dir}/restore.sql.gz"

    # Download if S3 path
    if [[ "$backup_path" == s3://* ]]; then
        download_from_s3 "$backup_path" "$local_file"
    else
        cp "$backup_path" "$local_file"
    fi

    # Find PostgreSQL pod
    local postgres_pod
    postgres_pod=$(find_postgres_pod)

    # Copy backup to pod
    log_info "Copying backup to pod..."
    gunzip -c "$local_file" | kubectl exec -i -n "$AWX_NAMESPACE" "$postgres_pod" -- \
        tee /tmp/restore.dump > /dev/null

    # Restore database
    log_info "Restoring database..."
    kubectl exec -n "$AWX_NAMESPACE" "$postgres_pod" -- \
        pg_restore -U "$AWX_DB_USER" -d "$AWX_DB_NAME" \
        --clean --if-exists \
        --verbose \
        /tmp/restore.dump 2>&1 | while read -r line; do
            log_debug "pg_restore: $line"
        done

    # Cleanup
    kubectl exec -n "$AWX_NAMESPACE" "$postgres_pod" -- \
        rm -f /tmp/restore.dump

    log_info "Restore completed successfully"
    send_slack_notification "success" "AWX database restored from backup" "Source: $backup_path"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    local dry_run=false
    local list_only=false
    local restore_path=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -n|--namespace)
                AWX_NAMESPACE="$2"
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
        list_backups
        exit 0
    fi

    # Restore mode
    if [[ -n "$restore_path" ]]; then
        check_required_vars "S3_BUCKET" "AWS_REGION"
        check_aws_credentials
        check_kubectl
        restore_backup "$restore_path"
        exit 0
    fi

    # Backup mode
    log_info "========================================"
    log_info "AWX Database Backup"
    log_info "========================================"
    log_info "Environment: $ENVIRONMENT"
    log_info "Date: $BACKUP_DATE"
    log_info "S3 Bucket: $S3_BUCKET"
    log_info "========================================"

    # Validation
    check_required_vars "${REQUIRED_VARS[@]}"
    check_aws_credentials
    check_kubectl

    if [[ "$dry_run" == "true" ]]; then
        log_info "[DRY RUN] Would backup to: $S3_PATH"
        exit 0
    fi

    # Create temp directory
    local temp_dir
    temp_dir=$(create_temp_dir "awx-backup")
    trap "cleanup_temp_dir '$temp_dir'" EXIT

    # Find PostgreSQL pod
    local postgres_pod
    postgres_pod=$(find_postgres_pod)

    # Perform backup
    local backup_file
    backup_file=$(perform_backup "$postgres_pod" "$temp_dir")

    # Upload to S3
    upload_backup "$backup_file"

    # Verify
    verify_backup

    # Success notification
    local backup_size=$(du -h "$backup_file" | cut -f1)
    send_slack_notification "success" "AWX database backup completed" "Size: $backup_size\nPath: $S3_PATH"

    log_info "========================================"
    log_info "Backup completed successfully!"
    log_info "S3 Path: $S3_PATH"
    log_info "========================================"
}

main "$@"
