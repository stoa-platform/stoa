#!/bin/bash
# Rules budget lint — validates AI Factory token budget constraints.
# Runs as a Stop hook to report budget status and log metrics.
# Can also be run standalone: bash .claude/hooks/rules-budget-lint.sh
#
# Thresholds:
#   - Any rule without globs must be < 5K bytes (except workflow-essentials.md)
#   - Total always-loaded (no globs) must be < 10K bytes
#   - MEMORY.md must be < 120 lines

RULES_DIR="$CLAUDE_PROJECT_DIR/.claude/rules"
MEMORY_FILE="$CLAUDE_PROJECT_DIR/memory.md"
METRICS_LOG="$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/metrics.log"

# Fallback for standalone execution
[ -z "$CLAUDE_PROJECT_DIR" ] && RULES_DIR="$(cd "$(dirname "$0")/.." && pwd)/rules" && MEMORY_FILE="$(cd "$(dirname "$0")/../.." && pwd)/memory.md"

MAX_UNSCOPED_BYTES=5120    # 5K per file
MAX_ALWAYS_LOADED=10240    # 10K total
MAX_MEMORY_LINES=120
EXCEPTION="workflow-essentials.md"

ERRORS=0
ALWAYS_LOADED_BYTES=0
FILES_WITHOUT_GLOBS=0

# Check each rule file
for f in "$RULES_DIR"/*.md; do
  [ ! -f "$f" ] && continue
  filename=$(basename "$f")
  size=$(wc -c < "$f" | tr -d ' ')
  has_globs=$(head -5 "$f" | grep -c "^globs:" || true)

  if [ "$has_globs" -eq 0 ]; then
    FILES_WITHOUT_GLOBS=$((FILES_WITHOUT_GLOBS + 1))
    ALWAYS_LOADED_BYTES=$((ALWAYS_LOADED_BYTES + size))

    # Check per-file threshold (skip exception)
    if [ "$filename" != "$EXCEPTION" ] && [ "$size" -gt "$MAX_UNSCOPED_BYTES" ]; then
      echo "BUDGET VIOLATION: $filename is ${size}B without globs (max ${MAX_UNSCOPED_BYTES}B)"
      ERRORS=$((ERRORS + 1))
    fi
  fi
done

# Check total always-loaded budget
if [ "$ALWAYS_LOADED_BYTES" -gt "$MAX_ALWAYS_LOADED" ]; then
  echo "BUDGET VIOLATION: always-loaded rules total ${ALWAYS_LOADED_BYTES}B (max ${MAX_ALWAYS_LOADED}B)"
  ERRORS=$((ERRORS + 1))
fi

# Check MEMORY.md line count
if [ -f "$MEMORY_FILE" ]; then
  MEMORY_LINES=$(wc -l < "$MEMORY_FILE" | tr -d ' ')
  if [ "$MEMORY_LINES" -gt "$MAX_MEMORY_LINES" ]; then
    echo "BUDGET WARNING: memory.md has ${MEMORY_LINES} lines (max ${MAX_MEMORY_LINES})"
  fi
else
  MEMORY_LINES=0
fi

# Log metrics
if [ -n "$METRICS_LOG" ] && [ -d "$(dirname "$METRICS_LOG")" ]; then
  echo "$(date +%Y-%m-%dT%H:%M) | RULES-BUDGET | always_loaded_bytes=$ALWAYS_LOADED_BYTES files_without_globs=$FILES_WITHOUT_GLOBS memory_lines=$MEMORY_LINES" >> "$METRICS_LOG"
fi

# Summary (only if violations)
if [ "$ERRORS" -gt 0 ]; then
  echo "Rules budget: $ERRORS violation(s). Fix before committing."
fi

# Always exit 0 — warn-only hook (same pattern as stop-state-lint.sh)
exit 0
