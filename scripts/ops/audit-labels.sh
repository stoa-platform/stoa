#!/usr/bin/env bash
# audit-labels.sh — Audit K8s resources for STOA label taxonomy compliance (CAB-1877)
#
# Usage:
#   ./scripts/ops/audit-labels.sh                    # Default: stoa-system namespace, prod kubeconfig
#   ./scripts/ops/audit-labels.sh -n stoa-monitoring  # Custom namespace
#   ./scripts/ops/audit-labels.sh --fix               # Suggest kubectl label commands
#   ./scripts/ops/audit-labels.sh --json              # JSON output for automation
#
# Required labels:
#   app.kubernetes.io/part-of       (enforced by Kyverno require-labels)
#   app.kubernetes.io/component     (enforced by Kyverno require-lifecycle-labels)
#   stoa.dev/environment            (enforced by Kyverno require-lifecycle-labels)
#   stoa.dev/managed-by             (enforced by Kyverno require-lifecycle-labels)

set -euo pipefail

NAMESPACE="${NAMESPACE:-stoa-system}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-stoa-ovh}"
FIX_MODE=false
JSON_MODE=false
RESOURCE_TYPES="deployments,statefulsets,cronjobs"

# Required labels
REQUIRED_LABELS=(
  "app.kubernetes.io/part-of"
  "app.kubernetes.io/component"
  "stoa.dev/environment"
  "stoa.dev/managed-by"
)

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--namespace) NAMESPACE="$2"; shift 2 ;;
    --fix) FIX_MODE=true; shift ;;
    --json) JSON_MODE=true; shift ;;
    -h|--help)
      echo "Usage: $0 [-n namespace] [--fix] [--json]"
      echo "  -n, --namespace  K8s namespace (default: stoa-system)"
      echo "  --fix            Output kubectl label commands to fix violations"
      echo "  --json           JSON output for automation"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

export KUBECONFIG

# Collect all resources
resources=$(kubectl get "$RESOURCE_TYPES" -n "$NAMESPACE" -o json 2>/dev/null)
if [[ -z "$resources" ]] || [[ "$(echo "$resources" | jq '.items | length')" == "0" ]]; then
  echo "No resources found in namespace $NAMESPACE"
  exit 0
fi

total=0
compliant=0
violations=()
json_results=()

# Check each resource
for row in $(echo "$resources" | jq -r '.items[] | @base64'); do
  _jq() { echo "$row" | base64 --decode | jq -r "$1"; }

  kind=$(_jq '.kind')
  name=$(_jq '.metadata.name')
  labels=$(_jq '.metadata.labels // {}')
  total=$((total + 1))

  missing=()
  for label in "${REQUIRED_LABELS[@]}"; do
    value=$(echo "$labels" | jq -r --arg l "$label" '.[$l] // empty')
    if [[ -z "$value" ]]; then
      missing+=("$label")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    compliant=$((compliant + 1))
  else
    violations+=("$kind/$name: missing ${missing[*]}")

    if $JSON_MODE; then
      json_results+=("{\"kind\":\"$kind\",\"name\":\"$name\",\"missing\":[$(printf '"%s",' "${missing[@]}" | sed 's/,$//')]}")
    fi

    if $FIX_MODE; then
      echo "# Fix: $kind/$name"
      for label in "${missing[@]}"; do
        case "$label" in
          "app.kubernetes.io/part-of")
            echo "kubectl label $kind $name -n $NAMESPACE app.kubernetes.io/part-of=stoa-platform" ;;
          "app.kubernetes.io/component")
            echo "kubectl label $kind $name -n $NAMESPACE app.kubernetes.io/component=FIXME" ;;
          "stoa.dev/environment")
            echo "kubectl label $kind $name -n $NAMESPACE stoa.dev/environment=prod" ;;
          "stoa.dev/managed-by")
            echo "kubectl label $kind $name -n $NAMESPACE stoa.dev/managed-by=argocd" ;;
        esac
      done
      echo ""
    fi
  fi
done

# Output
if $JSON_MODE; then
  echo "{"
  echo "  \"namespace\": \"$NAMESPACE\","
  echo "  \"total\": $total,"
  echo "  \"compliant\": $compliant,"
  echo "  \"violations\": $((total - compliant)),"
  echo "  \"compliance_pct\": $(( compliant * 100 / (total > 0 ? total : 1) )),"
  echo "  \"details\": [$(IFS=,; echo "${json_results[*]:-}")]"
  echo "}"
else
  echo "=== STOA Label Audit Report ==="
  echo "Namespace:  $NAMESPACE"
  echo "Resources:  $total"
  echo "Compliant:  $compliant"
  echo "Violations: $((total - compliant))"
  echo "Score:      $(( compliant * 100 / (total > 0 ? total : 1) ))%"
  echo ""

  if [[ ${#violations[@]} -gt 0 ]]; then
    echo "--- Violations ---"
    for v in "${violations[@]}"; do
      echo "  ✗ $v"
    done
    echo ""
    if ! $FIX_MODE; then
      echo "Run with --fix to get kubectl commands to remediate."
    fi
  else
    echo "All resources compliant ✓"
  fi
fi
