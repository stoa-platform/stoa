#!/usr/bin/env bash
# =============================================================================
# catalog-graph.sh — Generate Mermaid dependency graph from platform-catalog.yaml
# =============================================================================
# Reads the catalog and outputs a Mermaid flowchart to docs/architecture-graph.md
#
# Usage:
#   ./scripts/ops/catalog-graph.sh              # Generate graph
#   ./scripts/ops/catalog-graph.sh --check      # Check if graph is up-to-date
#
# Requirements: yq (https://github.com/mikefarah/yq)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CATALOG_PATH="$REPO_ROOT/docs/platform-catalog.yaml"
OUTPUT_PATH="$REPO_ROOT/docs/architecture-graph.md"

CHECK_MODE=false
for arg in "$@"; do
  case $arg in
    --check) CHECK_MODE=true ;;
  esac
done

if ! command -v yq &>/dev/null; then
  echo "Error: yq is required. Install: brew install yq" >&2
  exit 1
fi

if [ ! -f "$CATALOG_PATH" ]; then
  echo "Error: Catalog not found at $CATALOG_PATH" >&2
  exit 1
fi

# =============================================================================
# Generate Mermaid content
# =============================================================================
generate_graph() {
  local LAST_UPDATED
  LAST_UPDATED=$(yq '.metadata.lastUpdated' "$CATALOG_PATH")

  cat <<HEADER
# Platform Architecture — Dependency Graph

> Auto-generated from \`docs/platform-catalog.yaml\` by \`scripts/ops/catalog-graph.sh\`.
> Last catalog update: $LAST_UPDATED. Do not edit manually.

## Service Dependencies

\`\`\`mermaid
graph TD
    %% Style definitions
    classDef backend fill:#4f46e5,stroke:#312e81,color:#fff
    classDef frontend fill:#059669,stroke:#064e3b,color:#fff
    classDef gateway fill:#dc2626,stroke:#7f1d1d,color:#fff
    classDef database fill:#d97706,stroke:#78350f,color:#fff
    classDef identity fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef monitoring fill:#0284c7,stroke:#0c4a6e,color:#fff
    classDef messaging fill:#ea580c,stroke:#7c2d12,color:#fff
    classDef external fill:#6b7280,stroke:#374151,color:#fff

HEADER

  # Emit node declarations with display names
  yq -r '.services[] | "\(.name)|\(.displayName)|\(.type)"' "$CATALOG_PATH" | while IFS='|' read -r name display type; do
    # Sanitize name for Mermaid (replace hyphens)
    local mermaid_id="${name//-/_}"
    local class=""
    case "$type" in
      backend)           class="backend" ;;
      frontend)          class="frontend" ;;
      gateway|gateway-benchmark|gateway-external) class="gateway" ;;
      database|search)   class="database" ;;
      identity|secrets)  class="identity" ;;
      monitoring|logging) class="monitoring" ;;
      messaging)         class="messaging" ;;
      operator|gitops|automation) class="external" ;;
      *)                 class="" ;;
    esac

    echo "    ${mermaid_id}[\"${display}\"]"
    if [ -n "$class" ]; then
      echo "    class ${mermaid_id} ${class}"
    fi
  done

  echo ""
  echo "    %% Dependencies"

  # Emit edges (skip services with empty dependsOn)
  yq -r '.services[] | select(.dependsOn != null and (.dependsOn | length) > 0) | .name as $src | .dependsOn[] | "\($src)|\(.)"' "$CATALOG_PATH" | while IFS='|' read -r src dst; do
    [ -z "$dst" ] && continue
    local src_id="${src//-/_}"
    local dst_id="${dst//-/_}"
    echo "    ${src_id} --> ${dst_id}"
  done

  echo '```'

  # Service count table
  cat <<TABLE

## Service Inventory Summary

| Type | Count | Services |
|------|-------|----------|
TABLE

  for stype in backend frontend gateway database identity monitoring messaging automation gitops operator search logging secrets; do
    local count
    count=$(yq "[.services[] | select(.type == \"$stype\")] | length" "$CATALOG_PATH")
    if [ "$count" -gt 0 ]; then
      local names
      names=$(yq -r "[.services[] | select(.type == \"$stype\") | .name] | join(\", \")" "$CATALOG_PATH")
      echo "| $stype | $count | $names |"
    fi
  done

  # Also count benchmark + external gateways
  for stype in gateway-benchmark gateway-external; do
    local count
    count=$(yq "[.services[] | select(.type == \"$stype\")] | length" "$CATALOG_PATH")
    if [ "$count" -gt 0 ]; then
      local names
      names=$(yq -r "[.services[] | select(.type == \"$stype\") | .name] | join(\", \")" "$CATALOG_PATH")
      echo "| $stype | $count | $names |"
    fi
  done

  cat <<FOOTER

## Cluster Topology

| Cluster | Provider | Nodes | Namespaces/Hosts |
|---------|----------|-------|------------------|
FOOTER

  yq -r '.clusters[] | "\(.displayName)|\(.provider)|\(.nodes)|\(.namespaces // .hosts | length)"' "$CATALOG_PATH" | while IFS='|' read -r display provider nodes ns_count; do
    echo "| $display | $provider | $nodes | $ns_count |"
  done
}

# =============================================================================
# Main
# =============================================================================

GENERATED=$(generate_graph)

if [ "$CHECK_MODE" = true ]; then
  if [ ! -f "$OUTPUT_PATH" ]; then
    echo "architecture-graph.md does not exist — run scripts/ops/catalog-graph.sh to generate"
    exit 1
  fi

  CURRENT=$(cat "$OUTPUT_PATH")
  if [ "$GENERATED" != "$CURRENT" ]; then
    echo "architecture-graph.md is out of date — run scripts/ops/catalog-graph.sh to regenerate"
    exit 1
  fi

  echo "architecture-graph.md is up to date"
  exit 0
fi

echo "$GENERATED" > "$OUTPUT_PATH"
echo "Generated $OUTPUT_PATH ($(wc -l < "$OUTPUT_PATH") lines)"
