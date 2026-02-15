#!/bin/bash
# Stop hook: warn Claude when memory.md has DONE items stuck in active sections.
# Runs on every Stop event. Warn-only (exit 0 always).
#
# Heading format dependency: expects "## " (H2) headings containing the section
# keywords "IN PROGRESS", "NEXT", "DONE". If memory.md heading format changes
# (e.g., different emoji, heading level, or wording), update extract_section().

MEMORY="$CLAUDE_PROJECT_DIR/memory.md"
[ ! -f "$MEMORY" ] && exit 0

METRICS_LOG="$HOME/.claude/projects/-Users-torpedo-CabIngenierie-Dropbox-Christophe-ABOULICAM--PERSO-stoa-platform-stoa/memory/metrics.log"
VIOLATIONS=0

# Extract section between an H2 heading containing $1 and the next H2 heading.
# Depends on memory.md using "## " prefix for section headings.
extract_section() {
  local heading="$1"
  sed -n "/^## .*${heading}/,/^## /{ /^## .*${heading}/d; /^## /d; p; }" "$MEMORY"
}

# Detect items where all sub-items are ✅ with zero [ ] remaining (implicit DONE).
# Scans multi-line blocks: a parent line followed by "- ✅" lines with no "- [ ]" lines.
count_all_done_subitems() {
  local section="$1"
  local count=0
  local has_check=0 has_open=0 in_block=0
  while IFS= read -r line; do
    # New top-level item starts a block
    if echo "$line" | grep -qE '^- '; then
      # Close previous block
      if [ "$in_block" -eq 1 ] && [ "$has_check" -gt 0 ] && [ "$has_open" -eq 0 ]; then
        count=$((count + 1))
      fi
      in_block=1; has_check=0; has_open=0
    fi
    # Sub-item with ✅
    if echo "$line" | grep -qE '^\s+- ✅'; then
      has_check=$((has_check + 1))
    fi
    # Sub-item with [ ] (still open)
    if echo "$line" | grep -qE '^\s+- \[ \]'; then
      has_open=$((has_open + 1))
    fi
  done <<< "$section"
  # Close last block
  if [ "$in_block" -eq 1 ] && [ "$has_check" -gt 0 ] && [ "$has_open" -eq 0 ]; then
    count=$((count + 1))
  fi
  echo "$count"
}

# Check IN PROGRESS section for DONE items
IN_PROGRESS=$(extract_section "IN PROGRESS")
if [ -n "$IN_PROGRESS" ]; then
  # Pattern 1: explicit DONE markers
  HITS=$(echo "$IN_PROGRESS" | grep -cE '\*\*DONE\*\*|— DONE' || true)
  # Pattern 2: all sub-items ✅ with no [ ] remaining
  IMPLICIT=$(count_all_done_subitems "$IN_PROGRESS")
  TOTAL=$((HITS + IMPLICIT))
  if [ "$TOTAL" -gt 0 ]; then
    echo "STATE LINT WARNING: $TOTAL item(s) marked DONE still in IN PROGRESS section of memory.md"
    [ "$IMPLICIT" -gt 0 ] && echo "  ($IMPLICIT item(s) have all sub-items checked with no open items remaining)"
    echo "  Move them to the DONE section before ending this session."
    VIOLATIONS=$((VIOLATIONS + TOTAL))
  fi
fi

# Check NEXT section for DONE items
NEXT=$(extract_section "NEXT")
if [ -n "$NEXT" ]; then
  HITS=$(echo "$NEXT" | grep -cE '\*\*DONE\*\*|— DONE|~~.*~~' || true)
  IMPLICIT=$(count_all_done_subitems "$NEXT")
  TOTAL=$((HITS + IMPLICIT))
  if [ "$TOTAL" -gt 0 ]; then
    echo "STATE LINT WARNING: $TOTAL item(s) marked DONE or struck-through in NEXT section of memory.md"
    [ "$IMPLICIT" -gt 0 ] && echo "  ($IMPLICIT item(s) have all sub-items checked with no open items remaining)"
    echo "  Move completed items to DONE section, remove strikethroughs."
    VIOLATIONS=$((VIOLATIONS + TOTAL))
  fi
fi

# Log drift to metrics if violations found
if [ "$VIOLATIONS" -gt 0 ] && [ -n "$METRICS_LOG" ]; then
  echo "$(date +%Y-%m-%dT%H:%M) | STATE-DRIFT | items_misplaced=$VIOLATIONS" >> "$METRICS_LOG"
fi

exit 0
