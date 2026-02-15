#!/bin/bash
# Stop hook: warn Claude when memory.md has DONE items stuck in active sections.
# Runs on every Stop event. Warn-only (exit 0 always).

MEMORY="$CLAUDE_PROJECT_DIR/memory.md"
[ ! -f "$MEMORY" ] && exit 0

METRICS_LOG="$HOME/.claude/projects/-Users-torpedo-CabIngenierie-Dropbox-Christophe-ABOULICAM--PERSO-stoa-platform-stoa/memory/metrics.log"
VIOLATIONS=0

# Extract section between a heading and the next same-level heading
extract_section() {
  local heading="$1"
  sed -n "/^## .*${heading}/,/^## /{ /^## .*${heading}/d; /^## /d; p; }" "$MEMORY"
}

# Check IN PROGRESS section for DONE items
IN_PROGRESS=$(extract_section "IN PROGRESS")
if [ -n "$IN_PROGRESS" ]; then
  HITS=$(echo "$IN_PROGRESS" | grep -cE '\*\*DONE\*\*|— DONE' || true)
  if [ "$HITS" -gt 0 ]; then
    echo "STATE LINT WARNING: $HITS item(s) marked DONE still in IN PROGRESS section of memory.md"
    echo "  Move them to the DONE section before ending this session."
    VIOLATIONS=$((VIOLATIONS + HITS))
  fi
fi

# Check NEXT section for DONE items
NEXT=$(extract_section "NEXT")
if [ -n "$NEXT" ]; then
  HITS=$(echo "$NEXT" | grep -cE '\*\*DONE\*\*|— DONE|~~.*~~' || true)
  if [ "$HITS" -gt 0 ]; then
    echo "STATE LINT WARNING: $HITS item(s) marked DONE or struck-through in NEXT section of memory.md"
    echo "  Move completed items to DONE section, remove strikethroughs."
    VIOLATIONS=$((VIOLATIONS + HITS))
  fi
fi

# Log drift to metrics if violations found
if [ "$VIOLATIONS" -gt 0 ] && [ -n "$METRICS_LOG" ]; then
  echo "$(date +%Y-%m-%dT%H:%M) | STATE-DRIFT | items_misplaced=$VIOLATIONS" >> "$METRICS_LOG"
fi

exit 0
