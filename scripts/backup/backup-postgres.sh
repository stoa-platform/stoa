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

# Required environment variables (S3 destination only)
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

# How pg_dump/psql reach the database:
#   kubectl - run inside the PostgreSQL pod via `kubectl exec` (default)
#   direct  - run locally; connection comes from libpq env (PGHOST, PGPORT, PGPASSWORD...)
PG_CONNECTION_MODE="${PG_CONNECTION_MODE:-kubectl}"
# Where backups are stored: s3 (default) or local (BACKUP_LOCAL_DIR)
BACKUP_DESTINATION="${BACKUP_DESTINATION:-s3}"
BACKUP_LOCAL_DIR="${BACKUP_LOCAL_DIR:-}"

# Last lines of a complete plain-format pg_dump; a missing marker means truncation
PG_DUMP_COMPLETE_MARKER="PostgreSQL database dump complete"

# Derived values
BACKUP_FILENAME="stoa_backup_${BACKUP_TIMESTAMP}.sql.gz"
S3_PATH="s3://${S3_BUCKET:-stoa-backups}/postgres/${BACKUP_DATE}/${BACKUP_FILENAME}"

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Backup PostgreSQL database to S3 (or a local directory).

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
    S3_BUCKET               S3 bucket for backups (required for S3 destination)
    AWS_REGION              AWS region (required for S3 destination)
    PG_NAMESPACE            Kubernetes namespace (default: stoa-system)
    PG_POD_NAME             PostgreSQL pod name (default: control-plane-db-0)
    PG_DATABASE             Database name (default: stoa)
    PG_USER                 Database user (default: stoa)
    PG_CONNECTION_MODE      kubectl (default) or direct (uses PGHOST/PGPORT/PGPASSWORD)
    BACKUP_DESTINATION      s3 (default) or local
    BACKUP_LOCAL_DIR        Directory for backups when BACKUP_DESTINATION=local
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

    # Backup / restore a reachable database to a local directory (no kubectl, no S3)
    PG_CONNECTION_MODE=direct BACKUP_DESTINATION=local BACKUP_LOCAL_DIR=/tmp/backups ./backup-postgres.sh
    PG_CONNECTION_MODE=direct ./backup-postgres.sh --restore /tmp/backups/2024-01-15/stoa_backup.sql.gz --force
EOF
}

validate_config() {
    case "$PG_CONNECTION_MODE" in
        kubectl|direct) ;;
        *)
            log_error "Invalid PG_CONNECTION_MODE: $PG_CONNECTION_MODE (expected kubectl or direct)"
            return 1
            ;;
    esac

    case "$BACKUP_DESTINATION" in
        s3) ;;
        local)
            if [[ -z "$BACKUP_LOCAL_DIR" ]]; then
                log_error "BACKUP_LOCAL_DIR is required when BACKUP_DESTINATION=local"
                return 1
            fi
            ;;
        *)
            log_error "Invalid BACKUP_DESTINATION: $BACKUP_DESTINATION (expected s3 or local)"
            return 1
            ;;
    esac
}

# Run a PostgreSQL client command where the database is reachable.
# stdin is forwarded so SQL can be streamed in either mode.
pg_run() {
    if [[ "$PG_CONNECTION_MODE" == "kubectl" ]]; then
        kubectl exec -i -n "$PG_NAMESPACE" "$PG_POD_NAME" -- "$@"
    else
        "$@"
    fi
}

pg_psql() {
    local database=$1
    shift
    pg_run psql --no-psqlrc -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$database" "$@"
}

check_postgres_connectivity() {
    log_info "Checking PostgreSQL connectivity..."

    if [[ "$PG_CONNECTION_MODE" == "kubectl" ]]; then
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
    fi

    # Test database connection
    log_info "Testing database connection..."
    if pg_psql "$PG_DATABASE" -c "SELECT 1" &>/dev/null; then
        log_info "Database connection successful"
        return 0
    else
        log_error "Cannot connect to database"
        return 1
    fi
}

get_database_info() {
    log_info "Getting database information..."

    local db_size table_count pg_version
    db_size=$(pg_psql "$PG_DATABASE" -At -c "SELECT pg_size_pretty(pg_database_size(current_database()));")
    table_count=$(pg_psql "$PG_DATABASE" -At -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
    pg_version=$(pg_psql "$PG_DATABASE" -At -c "SHOW server_version;")

    log_info "Database: $PG_DATABASE"
    log_info "Size: $db_size"
    log_info "Tables: $table_count"
    log_info "PostgreSQL Version: $pg_version"
}

# Fail unless the file is a readable gzip holding a complete plain-format dump.
validate_backup_file() {
    local backup_file=$1

    if [[ ! -s "$backup_file" ]]; then
        log_error "Backup file is empty or missing: $backup_file"
        return 1
    fi

    if ! gunzip -t "$backup_file"; then
        log_error "Backup integrity check failed (invalid gzip): $backup_file"
        return 1
    fi

    local tail_lines
    # Newer pg_dump releases append a few lines (e.g. \unrestrict) after the marker
    tail_lines=$(gunzip -c "$backup_file" | tail -n 20)
    if [[ "$tail_lines" != *"$PG_DUMP_COMPLETE_MARKER"* ]]; then
        log_error "Backup is incomplete (missing pg_dump completion marker): $backup_file"
        return 1
    fi
}

# Prints the path of the local backup file on stdout.
perform_backup() {
    local temp_dir=$1
    local local_backup="${temp_dir}/${BACKUP_FILENAME}"
    local start_time=$(date +%s)

    log_info "Starting PostgreSQL backup..."
    log_info "  Database: $PG_DATABASE"
    log_info "  User: $PG_USER"
    log_info "  Mode: $PG_CONNECTION_MODE"
    [[ "$PG_CONNECTION_MODE" == "kubectl" ]] && log_info "  Pod: $PG_POD_NAME"

    # Create backup using pg_dump with compression; pg_dump errors stay visible on stderr
    log_info "Running pg_dump..."
    if pg_run pg_dump -U "$PG_USER" -d "$PG_DATABASE" \
        --no-owner \
        --no-privileges \
        --format=plain | gzip > "$local_backup"; then
        log_info "pg_dump completed successfully"
    else
        log_error "pg_dump failed"
        return 1
    fi

    log_info "Verifying backup integrity..."
    validate_backup_file "$local_backup"
    log_info "Backup integrity verified"

    local backup_size=$(du -h "$local_backup" | cut -f1)
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_info "Backup completed: $backup_size in $(format_duration $duration)"

    echo "$local_backup"
}

# Prints the final backup location on stdout.
store_backup() {
    local local_file=$1

    if [[ "$BACKUP_DESTINATION" == "local" ]]; then
        local dest_dir="${BACKUP_LOCAL_DIR}/${BACKUP_DATE}"
        mkdir -p "$dest_dir"
        cp "$local_file" "${dest_dir}/${BACKUP_FILENAME}"
        log_info "Backup stored locally: ${dest_dir}/${BACKUP_FILENAME}"
        echo "${dest_dir}/${BACKUP_FILENAME}"
        return 0
    fi

    upload_backup "$local_file"
    verify_backup
    cleanup_old_backups
    echo "$S3_PATH"
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
            # Not ((deleted_count++)): it returns 1 when the old value is 0 and trips set -e
            deleted_count=$((deleted_count + 1))
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

    # Download if S3 path
    if [[ "$backup_path" == s3://* ]]; then
        download_from_s3 "$backup_path" "$local_file"
    else
        cp "$backup_path" "$local_file"
    fi

    # Validate before touching the live database: a corrupt or truncated
    # backup must never cause the current data to be dropped.
    log_info "Validating backup..."
    validate_backup_file "$local_file"
    log_info "Backup is complete and readable"

    # Drop and recreate database (if not the default postgres db)
    if [[ "$PG_DATABASE" != "postgres" ]]; then
        log_info "Dropping and recreating database..."
        # Open sessions would make DROP DATABASE fail, so terminate them first.
        # Identifiers are passed as psql variables to keep them quoted.
        pg_psql postgres -q -v db="$PG_DATABASE" -v owner="$PG_USER" <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
 WHERE datname = :'db' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS :"db";
CREATE DATABASE :"db" OWNER :"owner";
SQL
    fi

    # Restore database in one transaction; ON_ERROR_STOP makes any SQL error fatal
    log_info "Restoring database from backup..."
    if gunzip -c "$local_file" | pg_psql "$PG_DATABASE" -q --single-transaction >/dev/null; then
        log_info "Database restore completed"
    else
        log_error "Database restore failed"
        return 1
    fi

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

    validate_config

    # List mode
    if [[ "$list_only" == "true" ]]; then
        check_required_vars "S3_BUCKET"
        check_aws_credentials
        list_backups
        exit 0
    fi

    # Restore mode
    if [[ -n "$restore_path" ]]; then
        # AWS is only needed to fetch the backup from S3
        if [[ "$restore_path" == s3://* ]]; then
            check_required_vars "S3_BUCKET" "AWS_REGION"
            check_aws_credentials
        elif [[ ! -f "$restore_path" ]]; then
            log_error "Backup file not found: $restore_path"
            exit 1
        fi
        [[ "$PG_CONNECTION_MODE" == "kubectl" ]] && check_kubectl
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
    log_info "Connection mode: $PG_CONNECTION_MODE"
    [[ "$PG_CONNECTION_MODE" == "kubectl" ]] && log_info "Namespace: $PG_NAMESPACE"
    [[ "$PG_CONNECTION_MODE" == "kubectl" ]] && log_info "Pod: $PG_POD_NAME"
    log_info "Database: $PG_DATABASE"
    log_info "Destination: $BACKUP_DESTINATION"
    log_info "========================================"

    # Validation
    if [[ "$BACKUP_DESTINATION" == "s3" ]]; then
        check_required_vars "${REQUIRED_VARS[@]}"
        check_aws_credentials
        # Update S3_PATH after S3_BUCKET is validated
        S3_PATH="s3://${S3_BUCKET}/postgres/${BACKUP_DATE}/${BACKUP_FILENAME}"
    fi
    [[ "$PG_CONNECTION_MODE" == "kubectl" ]] && check_kubectl
    check_postgres_connectivity

    if [[ "$dry_run" == "true" ]]; then
        if [[ "$BACKUP_DESTINATION" == "s3" ]]; then
            log_info "[DRY RUN] Would backup to: $S3_PATH"
        else
            log_info "[DRY RUN] Would backup to: ${BACKUP_LOCAL_DIR}/${BACKUP_DATE}/${BACKUP_FILENAME}"
        fi
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

    # Store (S3 upload + verification + retention, or local copy)
    local backup_location
    backup_location=$(store_backup "$backup_file")

    # Success notification
    local backup_size=$(du -h "$backup_file" | cut -f1)
    send_slack_notification "success" "PostgreSQL backup completed" "Database: $PG_DATABASE\nSize: $backup_size\nPath: $backup_location"

    log_info "========================================"
    log_info "Backup completed successfully!"
    log_info "Location: $backup_location"
    log_info "========================================"

    # Machine-readable result: the only line this script writes to stdout
    echo "$backup_location"
}

main "$@"
