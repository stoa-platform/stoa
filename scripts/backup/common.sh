#!/bin/bash
# =============================================================================
# Common Backup Functions
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# Shared functions for backup scripts
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export BACKUP_DATE=$(date +%Y-%m-%d)
export BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Logging Functions
# -----------------------------------------------------------------------------

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        DEBUG)
            [[ "$LOG_LEVEL" == "DEBUG" ]] && echo -e "${BLUE}[$timestamp] [DEBUG]${NC} $message"
            ;;
        INFO)
            echo -e "${GREEN}[$timestamp] [INFO]${NC} $message"
            ;;
        WARN)
            echo -e "${YELLOW}[$timestamp] [WARN]${NC} $message" >&2
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] [ERROR]${NC} $message" >&2
            ;;
    esac
}

log_info() { log INFO "$@"; }
log_warn() { log WARN "$@"; }
log_error() { log ERROR "$@"; }
log_debug() { log DEBUG "$@"; }

# -----------------------------------------------------------------------------
# Error Handling
# -----------------------------------------------------------------------------

# Global error handler
error_handler() {
    local exit_code=$?
    local line_number=$1
    log_error "Script failed at line $line_number with exit code $exit_code"

    # Send Slack notification on error
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        send_slack_notification "failure" "Backup failed at line $line_number (exit code: $exit_code)"
    fi

    exit $exit_code
}

# Set up trap for error handling
trap 'error_handler ${LINENO}' ERR

# -----------------------------------------------------------------------------
# Validation Functions
# -----------------------------------------------------------------------------

check_required_vars() {
    local vars=("$@")
    local missing=()

    for var in "${vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing+=("$var")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required environment variables: ${missing[*]}"
        return 1
    fi

    return 0
}

check_aws_credentials() {
    log_info "Checking AWS credentials..."

    if ! aws sts get-caller-identity &>/dev/null; then
        log_error "AWS credentials are not configured or invalid"
        return 1
    fi

    local identity=$(aws sts get-caller-identity --output json)
    local account=$(echo "$identity" | jq -r '.Account')
    local arn=$(echo "$identity" | jq -r '.Arn')

    log_info "AWS Identity: $arn (Account: $account)"
    return 0
}

check_kubectl() {
    log_info "Checking kubectl connectivity..."

    if ! command -v kubectl &>/dev/null; then
        log_error "kubectl is not installed"
        return 1
    fi

    if ! kubectl cluster-info &>/dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    local context=$(kubectl config current-context)
    log_info "Connected to Kubernetes context: $context"
    return 0
}

# -----------------------------------------------------------------------------
# S3 Functions
# -----------------------------------------------------------------------------

upload_to_s3() {
    local local_file=$1
    local s3_path=$2
    local kms_key_id=${3:-}

    log_info "Uploading $local_file to $s3_path..."

    local aws_args=(
        "s3" "cp" "$local_file" "$s3_path"
        "--only-show-errors"
    )

    # Add KMS encryption if key provided
    if [[ -n "$kms_key_id" ]]; then
        aws_args+=(
            "--sse" "aws:kms"
            "--sse-kms-key-id" "$kms_key_id"
        )
    fi

    if aws "${aws_args[@]}"; then
        local size=$(du -h "$local_file" | cut -f1)
        log_info "Upload successful: $s3_path ($size)"
        return 0
    else
        log_error "Failed to upload to S3"
        return 1
    fi
}

download_from_s3() {
    local s3_path=$1
    local local_file=$2

    log_info "Downloading $s3_path to $local_file..."

    if aws s3 cp "$s3_path" "$local_file" --only-show-errors; then
        log_info "Download successful"
        return 0
    else
        log_error "Failed to download from S3"
        return 1
    fi
}

list_s3_backups() {
    local s3_prefix=$1
    local limit=${2:-10}

    log_info "Listing backups at $s3_prefix (last $limit)..."

    aws s3 ls "$s3_prefix" --recursive | sort -r | head -n "$limit"
}

cleanup_old_s3_backups() {
    local s3_prefix=$1
    local keep_count=${2:-7}

    log_info "Cleaning up old backups, keeping last $keep_count..."

    local files=$(aws s3 ls "$s3_prefix" --recursive | sort -r | tail -n +$((keep_count + 1)) | awk '{print $4}')

    if [[ -z "$files" ]]; then
        log_info "No old backups to clean up"
        return 0
    fi

    local bucket=$(echo "$s3_prefix" | sed 's|s3://||' | cut -d'/' -f1)

    echo "$files" | while read -r file; do
        if [[ -n "$file" ]]; then
            log_info "Deleting old backup: $file"
            aws s3 rm "s3://${bucket}/${file}"
        fi
    done
}

# -----------------------------------------------------------------------------
# Slack Notification Functions
# -----------------------------------------------------------------------------

send_slack_notification() {
    local status=$1
    local message=$2
    local details=${3:-""}

    if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
        log_debug "Slack webhook URL not configured, skipping notification"
        return 0
    fi

    local color
    local emoji
    case $status in
        success)
            color="#36a64f"
            emoji=":white_check_mark:"
            ;;
        failure)
            color="#dc3545"
            emoji=":x:"
            ;;
        warning)
            color="#ffc107"
            emoji=":warning:"
            ;;
        *)
            color="#6c757d"
            emoji=":information_source:"
            ;;
    esac

    local environment="${ENVIRONMENT:-unknown}"
    local component="${BACKUP_COMPONENT:-backup}"

    local payload=$(cat <<EOF
{
    "channel": "#ops-alerts",
    "username": "STOA Backup Bot",
    "icon_emoji": ":floppy_disk:",
    "attachments": [
        {
            "color": "$color",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "$emoji *Backup ${status^}*\n\n*Component:* ${component}\n*Environment:* ${environment}\n*Message:* ${message}"
                    }
                }
            ]
        }
    ]
}
EOF
)

    if [[ -n "$details" ]]; then
        payload=$(echo "$payload" | jq --arg details "$details" '.attachments[0].blocks += [{"type": "section", "text": {"type": "mrkdwn", "text": "*Details:*\n```\($details)```"}}]')
    fi

    if curl -s -X POST -H 'Content-type: application/json' --data "$payload" "$SLACK_WEBHOOK_URL" &>/dev/null; then
        log_debug "Slack notification sent"
    else
        log_warn "Failed to send Slack notification"
    fi
}

# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------

create_temp_dir() {
    local prefix=${1:-backup}
    local temp_dir=$(mktemp -d -t "${prefix}-XXXXXXXXXX")
    log_debug "Created temp directory: $temp_dir"
    echo "$temp_dir"
}

cleanup_temp_dir() {
    local temp_dir=$1
    if [[ -d "$temp_dir" ]]; then
        rm -rf "$temp_dir"
        log_debug "Cleaned up temp directory: $temp_dir"
    fi
}

get_pod_name() {
    local namespace=$1
    local selector=$2

    kubectl get pods -n "$namespace" -l "$selector" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

wait_for_pod_ready() {
    local namespace=$1
    local pod_name=$2
    local timeout=${3:-60}

    log_info "Waiting for pod $pod_name to be ready (timeout: ${timeout}s)..."

    if kubectl wait --for=condition=ready pod/"$pod_name" -n "$namespace" --timeout="${timeout}s"; then
        log_info "Pod $pod_name is ready"
        return 0
    else
        log_error "Pod $pod_name is not ready after ${timeout}s"
        return 1
    fi
}

format_duration() {
    local seconds=$1
    printf '%02d:%02d:%02d' $((seconds/3600)) $((seconds%3600/60)) $((seconds%60))
}

# -----------------------------------------------------------------------------
# Main Check
# -----------------------------------------------------------------------------

# Only run checks if this script is being sourced for actual backup
if [[ "${BACKUP_DRY_RUN:-false}" != "true" ]]; then
    log_debug "Common functions loaded"
fi
