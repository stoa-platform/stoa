#!/bin/bash
# =============================================================================
# PostgreSQL Backup Script
# =============================================================================
# STOA Platform - CAB-309
# Backs up PostgreSQL database to S3 with optional KMS encryption
# Supports daily backups with 7-day retention
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

export BACKUP_COMPONENT="postgres"

# Required environment variables
REQUIRED_VARS=(
    "S3_BUCKET"
    "AWS_REGION"
)

# Optional with defaults
PG_NAMESPACE="${PG_NAMESPACE:-stoa-system}"
PG_POD_NAME="${PG_POD_NAME:-control-plane-db-0}"
PG_DATABASE="${PG_DATABASE:-stoa}"
PG_USER="${PG_USER:-stoa}"
KMS_KEY_ID="${KMS_KEY_ID:-}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

# Derived values
BACKUP_FILENAME="stoa_backup_${BACKUP_TIMESTAMP}.sql.gz"
S3_PATH="s3://${S3_BUCKET:-stoa-backups}/postgres/${BACKUP_DATE}/${BACKUP_FILENAME}"

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Backup PostgreSQL database to S3.

Options:
    -h, --help              Show this help message
    -n, --namespace NAME    Kubernetes namespace (default: stoa-system)
    -p, --pod NAME          PostgreSQL pod name (default: control-plane-db-0)
    -d, --database NAME     Database name (default: stoa)
    -u, --user NAME         Database user (default: stoa)
    --dry-run               Dry run - show what would be done
    -v, --verbose           Enable verbose output
    -l, --list              List available backups
    --restore FILE          Restore from backup (S3 path or local file)
    --force                 Force restore without confirmation

Environment Variables:
    S3_BUCKET               S3 bucket for backups (required)
    AWS_REGION              AWS region (required)
    PG_NAMESPACE            Kubernetes namespace (default: stoa-system)
    PG_POD_NAME             PostgreSQL pod name (default: control-plane-db-0)
    PG_DATABASE             Database name (default: stoa)
    PG_USER                 Database user (default: stoa)
    KMS_KEY_ID              KMS key ID for encryption (optional)
    BACKUP_RETENTION_DAYS   Days to keep backups (default: 7)
    SLACK_WEBHOOK_URL       Slack webhook for notifications (optional)

Examples:
    # Run backup
    S3_BUCKET=stoa-backups AWS_REGION=eu-west-1 ./backup-postgres.sh

    # List existing backups
    S3_BUCKET=stoa-backups ./backup-postgres.sh --list

    # Restore from backup
    S3_BUCKET=stoa-backups ./backup-postgres.sh --restore s3://stoa-backups/postgres/2024-01-15/stoa_backup.sql.gz

    # Dry run
    S3_BUCKET=stoa-backups ./backup-postgres.sh --dry-run
EOF
}

check_postgres_connectivity() {
    log_info "Checking PostgreSQL connectivity..."

    # Verify pod exists and is running
    local pod_status
    pod_status=$(kubectl get pod "$PG_POD_NAME" -n "$PG_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null) || {
        log_error "Pod $PG_POD_NAME not found in namespace $PG_NAMESPACE"
        return 1
    }

    if [[ "$pod_status" != "Running" ]]; then
        log_error "Pod $PG_POD_NAME is not running (status: $pod_status)"
        return 1
    fi

    log_info "Pod $PG_POD_NAME is running"

    # Test database connection
    log_info "Testing database connection..."
    if kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
        psql -U "$PG_USER" -d "$PG_DATABASE" -c "SELECT 1" &>/dev/null; then
        log_info "Database connection successful"
        return 0
    else
        log_error "Cannot connect to database"
        return 1
    fi
}

get_database_info() {
    log_info "Getting database information..."

    # Get database size
    local db_size
    db_size=$(kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
        psql -U "$PG_USER" -d "$PG_DATABASE" -t -c \
        "SELECT pg_size_pretty(pg_database_size('$PG_DATABASE'));" 2>/dev/null | tr -d ' ')

    # Get table count
    local table_count
    table_count=$(kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
        psql -U "$PG_USER" -d "$PG_DATABASE" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')

    # Get PostgreSQL version
    local pg_version
    pg_version=$(kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
        psql -U "$PG_USER" -d "$PG_DATABASE" -t -c "SELECT version();" 2>/dev/null | head -1 | awk '{print $2}')

    log_info "Database: $PG_DATABASE"
    log_info "Size: $db_size"
    log_info "Tables: $table_count"
    log_info "PostgreSQL Version: $pg_version"
}

perform_backup() {
    local temp_dir=$1
    local local_backup="${temp_dir}/${BACKUP_FILENAME}"
    local start_time=$(date +%s)

    log_info "Starting PostgreSQL backup..."
    log_info "  Database: $PG_DATABASE"
    log_info "  User: $PG_USER"
    log_info "  Pod: $PG_POD_NAME"

    # Create backup using pg_dump with compression
    log_info "Running pg_dump..."
    if kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
        pg_dump -U "$PG_USER" -d "$PG_DATABASE" \
        --no-owner \
        --no-privileges \
        --format=plain \
        --verbose 2>/dev/null | gzip > "$local_backup"; then
        log_info "pg_dump completed successfully"
    else
        log_error "pg_dump failed"
        return 1
    fi

    # Verify backup file
    if [[ ! -f "$local_backup" ]] || [[ ! -s "$local_backup" ]]; then
        log_error "Backup file is empty or missing"
        return 1
    fi

    local backup_size=$(du -h "$local_backup" | cut -f1)
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_info "Backup completed: $backup_size in $(format_duration $duration)"

    # Verify backup integrity (test gunzip)
    log_info "Verifying backup integrity..."
    if gunzip -t "$local_backup"; then
        log_info "Backup integrity verified"
    else
        log_error "Backup integrity check failed"
        return 1
    fi

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
    log_info "Listing PostgreSQL backups in S3..."
    echo ""
    echo "Available backups (most recent first):"
    echo "=========================================="
    list_s3_backups "s3://${S3_BUCKET}/postgres/" 20
    echo ""
}

cleanup_old_backups() {
    log_info "Cleaning up backups older than $BACKUP_RETENTION_DAYS days..."

    # Get list of all backup files
    local files
    files=$(aws s3 ls "s3://${S3_BUCKET}/postgres/" --recursive 2>/dev/null | sort -r)

    if [[ -z "$files" ]]; then
        log_info "No backups found to clean up"
        return 0
    fi

    # Calculate cutoff date
    local cutoff_date
    if [[ "$(uname)" == "Darwin" ]]; then
        cutoff_date=$(date -v-${BACKUP_RETENTION_DAYS}d +%Y-%m-%d)
    else
        cutoff_date=$(date -d "-${BACKUP_RETENTION_DAYS} days" +%Y-%m-%d)
    fi

    log_info "Removing backups older than: $cutoff_date"

    local deleted_count=0
    while IFS= read -r line; do
        # Extract date from S3 listing (format: YYYY-MM-DD HH:MM:SS)
        local file_date=$(echo "$line" | awk '{print $1}')
        local file_path=$(echo "$line" | awk '{print $4}')

        if [[ "$file_date" < "$cutoff_date" ]] && [[ -n "$file_path" ]]; then
            log_info "Deleting old backup: $file_path"
            aws s3 rm "s3://${S3_BUCKET}/${file_path}"
            ((deleted_count++))
        fi
    done <<< "$files"

    log_info "Cleaned up $deleted_count old backup(s)"
}

# -----------------------------------------------------------------------------
# Restore Function
# -----------------------------------------------------------------------------

restore_backup() {
    local backup_path=$1
    local force=${2:-false}
    local temp_dir
    temp_dir=$(create_temp_dir "postgres-restore")

    trap "cleanup_temp_dir '$temp_dir'" EXIT

    log_info "Starting PostgreSQL restore..."
    log_warn "This will REPLACE the current database data!"
    log_warn "Database: $PG_DATABASE"

    # Confirm restore
    if [[ "$force" != "true" ]]; then
        read -p "Are you sure you want to proceed? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Restore cancelled"
            return 0
        fi
    fi

    local local_file="${temp_dir}/restore.sql.gz"
    local sql_file="${temp_dir}/restore.sql"

    # Download if S3 path
    if [[ "$backup_path" == s3://* ]]; then
        download_from_s3 "$backup_path" "$local_file"
    else
        cp "$backup_path" "$local_file"
    fi

    # Decompress
    log_info "Decompressing backup..."
    gunzip -c "$local_file" > "$sql_file"

    local sql_size=$(du -h "$sql_file" | cut -f1)
    log_info "Decompressed size: $sql_size"

    # Copy SQL file to pod
    log_info "Copying backup to pod..."
    kubectl cp "$sql_file" "$PG_NAMESPACE/$PG_POD_NAME:/tmp/restore.sql"

    # Drop and recreate database (if not the default postgres db)
    if [[ "$PG_DATABASE" != "postgres" ]]; then
        log_info "Dropping existing database..."
        kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
            psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS $PG_DATABASE;" || true

        log_info "Creating fresh database..."
        kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
            psql -U "$PG_USER" -d postgres -c "CREATE DATABASE $PG_DATABASE OWNER $PG_USER;"
    fi

    # Restore database
    log_info "Restoring database from backup..."
    if kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
        psql -U "$PG_USER" -d "$PG_DATABASE" -f /tmp/restore.sql; then
        log_info "Database restore completed"
    else
        log_error "Database restore failed"
        return 1
    fi

    # Cleanup
    log_info "Cleaning up temporary files on pod..."
    kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- rm -f /tmp/restore.sql

    # Verify restore
    log_info "Verifying restore..."
    get_database_info

    log_info "Restore completed successfully"
    send_slack_notification "success" "PostgreSQL restored from backup" "Source: $backup_path"
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
                PG_NAMESPACE="$2"
                shift 2
                ;;
            -p|--pod)
                PG_POD_NAME="$2"
                shift 2
                ;;
            -d|--database)
                PG_DATABASE="$2"
                shift 2
                ;;
            -u|--user)
                PG_USER="$2"
                shift 2
                ;;
            --dry-run)
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
        list_backups
        exit 0
    fi

    # Restore mode
    if [[ -n "$restore_path" ]]; then
        check_required_vars "S3_BUCKET" "AWS_REGION"
        check_aws_credentials
        check_kubectl
        check_postgres_connectivity
        restore_backup "$restore_path" "$force"
        exit 0
    fi

    # Backup mode
    log_info "========================================"
    log_info "PostgreSQL Database Backup"
    log_info "========================================"
    log_info "Environment: $ENVIRONMENT"
    log_info "Date: $BACKUP_DATE"
    log_info "Namespace: $PG_NAMESPACE"
    log_info "Pod: $PG_POD_NAME"
    log_info "Database: $PG_DATABASE"
    log_info "S3 Bucket: ${S3_BUCKET:-not set}"
    log_info "========================================"

    # Validation
    check_required_vars "${REQUIRED_VARS[@]}"
    check_aws_credentials
    check_kubectl
    check_postgres_connectivity

    # Update S3_PATH after S3_BUCKET is validated
    S3_PATH="s3://${S3_BUCKET}/postgres/${BACKUP_DATE}/${BACKUP_FILENAME}"

    if [[ "$dry_run" == "true" ]]; then
        log_info "[DRY RUN] Would backup to: $S3_PATH"
        get_database_info
        exit 0
    fi

    # Get database info
    get_database_info

    # Create temp directory
    local temp_dir
    temp_dir=$(create_temp_dir "postgres-backup")
    trap "cleanup_temp_dir '$temp_dir'" EXIT

    # Perform backup
    local backup_file
    backup_file=$(perform_backup "$temp_dir")

    # Upload to S3
    upload_backup "$backup_file"

    # Verify
    verify_backup

    # Cleanup old backups
    cleanup_old_backups

    # Success notification
    local backup_size=$(du -h "$backup_file" | cut -f1)
    send_slack_notification "success" "PostgreSQL backup completed" "Database: $PG_DATABASE\nSize: $backup_size\nPath: $S3_PATH"

    log_info "========================================"
    log_info "Backup completed successfully!"
    log_info "S3 Path: $S3_PATH"
    log_info "========================================"
}

main "$@"
