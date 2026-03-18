#!/usr/bin/env bash
# resource-cleanup.sh — TTL-based resource cleanup for STOA platform (CAB-1878)
#
# Scans K8s resources with stoa.dev/ttl labels and identifies/deletes expired ones.
# Default: dry-run mode (reports only). Set CLEANUP_DRY_RUN=false for active deletion.
#
# Environment:
#   NAMESPACE         - K8s namespace (default: stoa-system)
#   KUBECONFIG        - Path to kubeconfig (default: in-cluster or ~/.kube/config-stoa-ovh)
#   CLEANUP_DRY_RUN   - true=report only, false=delete expired (default: true)
#   SLACK_WEBHOOK_URL - Slack webhook for notifications (optional)
#   N8N_WEBHOOK_URL   - n8n webhook for notifications (optional, preferred over Slack)
#
# TTL format: ISO 8601 duration — P7D (7 days), P30D (30 days), P90D (90 days)
# Label: stoa.dev/ttl on resource metadata
# Created-at: uses resource .metadata.creationTimestamp
#
# Safety:
#   - ArgoCD-managed resources (stoa.dev/managed-by=argocd) are ALWAYS exempt
#   - Helm-managed resources (stoa.dev/managed-by=helm) are ALWAYS exempt
#   - Only Deployments, StatefulSets, CronJobs, Jobs, ConfigMaps, Services scanned

set -euo pipefail

NAMESPACE="${NAMESPACE:-stoa-system}"
CLEANUP_DRY_RUN="${CLEANUP_DRY_RUN:-true}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
N8N_WEBHOOK_URL="${N8N_WEBHOOK_URL:-}"
RESOURCE_TYPES=("deployments" "statefulsets" "cronjobs" "jobs" "configmaps" "services")
EXEMPT_MANAGERS=("argocd" "helm")

NOW_EPOCH=$(date +%s)
expired_resources=()
cleaned_resources=()

# Parse ISO 8601 duration (P<N>D) to seconds
parse_ttl_seconds() {
  local ttl="$1"
  local days

  # Match PnD format (days only — sufficient for resource lifecycle)
  if [[ "$ttl" =~ ^P([0-9]+)D$ ]]; then
    days="${BASH_REMATCH[1]}"
    echo $((days * 86400))
  else
    echo "0"  # Unparseable TTL — treat as no TTL
  fi
}

# Check if resource is exempt from cleanup
is_exempt() {
  local managed_by="$1"
  for exempt in "${EXEMPT_MANAGERS[@]}"; do
    if [[ "$managed_by" == "$exempt" ]]; then
      return 0
    fi
  done
  return 1
}

# Send notification (n8n preferred, Slack fallback)
notify() {
  local message="$1"

  if [[ -n "$N8N_WEBHOOK_URL" ]]; then
    curl -sf -X POST "$N8N_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"$message\"}" >/dev/null 2>&1 || true
  elif [[ -n "$SLACK_WEBHOOK_URL" ]]; then
    curl -sf -X POST "$SLACK_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"$message\"}" >/dev/null 2>&1 || true
  fi
}

echo "=== STOA Resource Cleanup ==="
echo "Namespace:  $NAMESPACE"
echo "Dry-run:    $CLEANUP_DRY_RUN"
echo "Timestamp:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

for resource_type in "${RESOURCE_TYPES[@]}"; do
  # Get resources with stoa.dev/ttl label
  resources=$(kubectl get "$resource_type" -n "$NAMESPACE" \
    -l "stoa.dev/ttl" \
    -o json 2>/dev/null || echo '{"items":[]}')

  count=$(echo "$resources" | jq '.items | length')
  if [[ "$count" == "0" ]]; then
    continue
  fi

  echo "--- $resource_type ($count with TTL) ---"

  for row in $(echo "$resources" | jq -r '.items[] | @base64'); do
    _jq() { echo "$row" | base64 --decode | jq -r "$1"; }

    name=$(_jq '.metadata.name')
    ttl=$(_jq '.metadata.labels["stoa.dev/ttl"]')
    managed_by=$(_jq '.metadata.labels["stoa.dev/managed-by"] // "unknown"')
    created=$(_jq '.metadata.creationTimestamp')

    # Check exemption
    if is_exempt "$managed_by"; then
      echo "  SKIP $name (managed-by=$managed_by, exempt)"
      continue
    fi

    # Parse TTL
    ttl_seconds=$(parse_ttl_seconds "$ttl")
    if [[ "$ttl_seconds" == "0" ]]; then
      echo "  SKIP $name (unparseable TTL: $ttl)"
      continue
    fi

    # Calculate expiry
    created_epoch=$(date -d "$created" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$created" +%s 2>/dev/null || echo "0")
    if [[ "$created_epoch" == "0" ]]; then
      echo "  SKIP $name (cannot parse creation date: $created)"
      continue
    fi

    expiry_epoch=$((created_epoch + ttl_seconds))
    remaining_seconds=$((expiry_epoch - NOW_EPOCH))
    remaining_days=$((remaining_seconds / 86400))

    if [[ $remaining_seconds -le 0 ]]; then
      days_overdue=$(( (-remaining_seconds) / 86400 ))
      echo "  EXPIRED $name (TTL=$ttl, overdue by ${days_overdue}d, managed-by=$managed_by)"
      expired_resources+=("$resource_type/$name (TTL=$ttl, overdue ${days_overdue}d)")

      if [[ "$CLEANUP_DRY_RUN" == "false" ]]; then
        echo "  DELETING $resource_type/$name..."
        if kubectl delete "$resource_type" "$name" -n "$NAMESPACE" --wait=false 2>/dev/null; then
          cleaned_resources+=("$resource_type/$name")
          echo "  DELETED $resource_type/$name"
        else
          echo "  FAILED to delete $resource_type/$name"
        fi
      fi
    else
      if [[ $remaining_days -le 7 ]]; then
        echo "  WARNING $name (TTL=$ttl, expires in ${remaining_days}d)"
      else
        echo "  OK $name (TTL=$ttl, ${remaining_days}d remaining)"
      fi
    fi
  done
done

echo ""
echo "=== Summary ==="
echo "Expired:  ${#expired_resources[@]}"
echo "Cleaned:  ${#cleaned_resources[@]}"
echo "Mode:     $(if [[ "$CLEANUP_DRY_RUN" == "true" ]]; then echo "DRY-RUN"; else echo "ACTIVE"; fi)"

# Send notification if there are expired resources
if [[ ${#expired_resources[@]} -gt 0 ]]; then
  mode_label=$(if [[ "$CLEANUP_DRY_RUN" == "true" ]]; then echo "DRY-RUN"; else echo "CLEANED"; fi)
  resource_list=$(printf "• %s\n" "${expired_resources[@]}")

  message=":recycle: *STOA Resource Cleanup* ($mode_label)
*Namespace*: $NAMESPACE
*Expired resources*: ${#expired_resources[@]}
$resource_list"

  if [[ ${#cleaned_resources[@]} -gt 0 ]]; then
    cleaned_list=$(printf "• %s\n" "${cleaned_resources[@]}")
    message="$message

*Deleted*: ${#cleaned_resources[@]}
$cleaned_list"
  fi

  notify "$message"
  echo ""
  echo "Notification sent."
fi
