#!/usr/bin/env bash
# =============================================================================
# catalog-graph.sh — Generate Mermaid dependency graph from platform-catalog.yaml
# =============================================================================
# Reads the catalog and outputs dependency information in various formats.
#
# Usage:
#   ./scripts/ops/catalog-graph.sh                       # Generate full graph
#   ./scripts/ops/catalog-graph.sh --check               # Check if graph is up-to-date
#   ./scripts/ops/catalog-graph.sh --reverse <service>   # Reverse deps (who breaks if service dies)
#   ./scripts/ops/catalog-graph.sh --impact <service>    # Mermaid impact subgraph (colored by depth)
#
# Requirements: yq (https://github.com/mikefarah/yq)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CATALOG_PATH="$REPO_ROOT/docs/platform-catalog.yaml"
OUTPUT_PATH="$REPO_ROOT/docs/architecture-graph.md"

CHECK_MODE=false
REVERSE_SERVICE=""
IMPACT_SERVICE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK_MODE=true; shift ;;
    --reverse)
      [ $# -lt 2 ] && { echo "Error: --reverse requires a service name" >&2; exit 1; }
      REVERSE_SERVICE="$2"; shift 2 ;;
    --impact)
      [ $# -lt 2 ] && { echo "Error: --impact requires a service name" >&2; exit 1; }
      IMPACT_SERVICE="$2"; shift 2 ;;
    *) shift ;;
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
# Validate service exists in catalog
# =============================================================================
validate_service() {
  local svc="$1"
  local exists
  exists=$(yq "[.services[] | select(.name == \"$svc\")] | length" "$CATALOG_PATH")
  if [ "$exists" -eq 0 ]; then
    echo "Error: service '$svc' not found in catalog" >&2
    echo "Available services:" >&2
    yq -r '.services[].name' "$CATALOG_PATH" | sed 's/^/  /' >&2
    exit 1
  fi
}

# =============================================================================
# Build reverse dependency map and compute transitive closure via BFS
# =============================================================================
# Uses a temp directory with one file per service to simulate associative arrays
# (portable across bash versions without declare -A).
# =============================================================================
compute_reverse_closure() {
  local target="$1"
  local tmpdir
  tmpdir=$(mktemp -d)

  # Build reverse adjacency: for each edge A->B, record B has reverse dep A
  yq -r '.services[] | select(.dependsOn != null and (.dependsOn | length) > 0) | .name as $src | .dependsOn[] | "\(.)|\($src)"' "$CATALOG_PATH" | while IFS='|' read -r dep src; do
    [ -z "$dep" ] || [ -z "$src" ] && continue
    echo "$src" >> "$tmpdir/rev_$dep"
  done

  # BFS from target through reverse graph
  echo "$target" > "$tmpdir/queue"
  touch "$tmpdir/visited"
  touch "$tmpdir/result"

  while [ -s "$tmpdir/queue" ]; do
    local current
    current=$(head -1 "$tmpdir/queue")
    sed -i '' '1d' "$tmpdir/queue" 2>/dev/null || sed -i '1d' "$tmpdir/queue"

    # Skip if already visited
    if grep -qxF "$current" "$tmpdir/visited" 2>/dev/null; then
      continue
    fi
    echo "$current" >> "$tmpdir/visited"

    # Skip the target itself for results
    if [ "$current" != "$target" ]; then
      echo "$current" >> "$tmpdir/result"
    fi

    # Enqueue reverse dependents
    if [ -f "$tmpdir/rev_$current" ]; then
      while IFS= read -r neighbor; do
        if ! grep -qxF "$neighbor" "$tmpdir/visited" 2>/dev/null; then
          echo "$neighbor" >> "$tmpdir/queue"
        fi
      done < "$tmpdir/rev_$current"
    fi
  done

  # Compute depth for each impacted service (BFS layers)
  # Re-run BFS tracking depth
  echo "" > "$tmpdir/depth_result"
  echo "$target" > "$tmpdir/dqueue"
  echo "$target|0" > "$tmpdir/dvisited"

  while [ -s "$tmpdir/dqueue" ]; do
    local current
    current=$(head -1 "$tmpdir/dqueue")
    sed -i '' '1d' "$tmpdir/dqueue" 2>/dev/null || sed -i '1d' "$tmpdir/dqueue"

    local current_depth
    current_depth=$(grep "^${current}|" "$tmpdir/dvisited" | head -1 | cut -d'|' -f2)
    local next_depth=$((current_depth + 1))

    if [ -f "$tmpdir/rev_$current" ]; then
      while IFS= read -r neighbor; do
        if ! grep -q "^${neighbor}|" "$tmpdir/dvisited" 2>/dev/null; then
          echo "$neighbor|$next_depth" >> "$tmpdir/dvisited"
          echo "$neighbor" >> "$tmpdir/dqueue"
        fi
      done < "$tmpdir/rev_$current"
    fi
  done

  # Output: service|depth (excluding target)
  grep -v "^${target}|" "$tmpdir/dvisited" | sort -t'|' -k2 -n

  rm -rf "$tmpdir"
}

# =============================================================================
# --reverse <service>: Print reverse dependencies with depth
# =============================================================================
show_reverse() {
  local target="$1"
  validate_service "$target"

  local display
  display=$(yq -r ".services[] | select(.name == \"$target\") | .displayName" "$CATALOG_PATH")

  echo "## Reverse Dependencies — $display ($target)"
  echo ""
  echo "If **$target** goes down, these services are impacted:"
  echo ""

  local closure
  closure=$(compute_reverse_closure "$target")

  if [ -z "$closure" ]; then
    echo "*No services depend on $target (leaf node).*"
    return
  fi

  echo "| Service | Impact Depth | Type |"
  echo "|---------|-------------|------|"

  echo "$closure" | while IFS='|' read -r svc depth; do
    [ -z "$svc" ] && continue
    local stype
    stype=$(yq -r ".services[] | select(.name == \"$svc\") | .type" "$CATALOG_PATH")
    local label="direct"
    [ "$depth" -gt 1 ] && label="transitive (depth $depth)"
    echo "| $svc | $label | $stype |"
  done

  echo ""

  local total
  total=$(echo "$closure" | grep -c '|' || true)
  local direct
  direct=$(echo "$closure" | grep '|1$' | wc -l | tr -d ' ')
  local transitive
  transitive=$((total - direct))

  echo "**Total**: $total impacted ($direct direct, $transitive transitive)"
}

# =============================================================================
# --impact <service>: Generate colored Mermaid subgraph
# =============================================================================
show_impact() {
  local target="$1"
  validate_service "$target"

  local display
  display=$(yq -r ".services[] | select(.name == \"$target\") | .displayName" "$CATALOG_PATH")

  echo "## Impact Graph — $display ($target)"
  echo ""
  echo "Services impacted if **$target** goes down."
  echo ""
  echo '```mermaid'
  echo "graph TD"
  echo "    %% Impact styles"
  echo "    classDef down fill:#dc2626,stroke:#7f1d1d,color:#fff"
  echo "    classDef direct fill:#f97316,stroke:#9a3412,color:#fff"
  echo "    classDef transitive fill:#facc15,stroke:#854d0e,color:#000"
  echo ""

  local closure
  closure=$(compute_reverse_closure "$target")

  # Declare target node
  local target_id="${target//-/_}"
  echo "    ${target_id}[\"${display} ⛔\"]"
  echo "    class ${target_id} down"

  if [ -z "$closure" ]; then
    echo '```'
    echo ""
    echo "*No services depend on $target (leaf node).*"
    return
  fi

  # Declare impacted nodes
  echo "$closure" | while IFS='|' read -r svc depth; do
    [ -z "$svc" ] && continue
    local svc_display
    svc_display=$(yq -r ".services[] | select(.name == \"$svc\") | .displayName" "$CATALOG_PATH")
    local svc_id="${svc//-/_}"
    local class="transitive"
    [ "$depth" -eq 1 ] && class="direct"
    echo "    ${svc_id}[\"${svc_display}\"]"
    echo "    class ${svc_id} ${class}"
  done

  echo ""
  echo "    %% Dependency edges (reverse direction: target -.-> dependents)"

  # Collect all impacted service names for edge filtering
  local impacted_list
  impacted_list=$(echo "$closure" | cut -d'|' -f1)

  # Emit edges: for each impacted service, show which of its dependsOn are also in the subgraph
  echo "$closure" | while IFS='|' read -r svc depth; do
    [ -z "$svc" ] && continue
    local svc_id="${svc//-/_}"
    # Get this service's forward deps
    local deps
    deps=$(yq -r ".services[] | select(.name == \"$svc\") | .dependsOn // [] | .[]" "$CATALOG_PATH")
    for dep in $deps; do
      # Only show edge if dep is the target or is also impacted
      if [ "$dep" = "$target" ] || echo "$impacted_list" | grep -qxF "$dep"; then
        local dep_id="${dep//-/_}"
        echo "    ${svc_id} -.->|depends on| ${dep_id}"
      fi
    done
  done

  echo '```'

  echo ""
  echo "**Legend**: 🔴 Down | 🟠 Direct impact (depth 1) | 🟡 Transitive impact (depth 2+)"
}

# =============================================================================
# Generate Mermaid content (original full graph)
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

# Handle --reverse mode
if [ -n "$REVERSE_SERVICE" ]; then
  show_reverse "$REVERSE_SERVICE"
  exit 0
fi

# Handle --impact mode
if [ -n "$IMPACT_SERVICE" ]; then
  show_impact "$IMPACT_SERVICE"
  exit 0
fi

# Default: generate full graph
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
