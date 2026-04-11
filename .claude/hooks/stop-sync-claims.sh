#!/bin/bash
# Stop hook: sync claim files with Linear completion state.
#
# Problem solved: when an instance finishes a phase, it updates Linear (Done)
# but may not update the local claim file. The next instance sees stale state.
#
# Logic:
# 1. Find all MEGA claim files in .claude/claims/
# 2. For each phase with completed_at=null, check if ALL tickets are Done on Linear
# 3. If yes → set completed_at in the claim file
#
# This is idempotent: running it multiple times produces the same result.
# Gracefully degrades: no LINEAR_API_KEY = silent skip.
#
# Kill-switch: DISABLE_CLAIM_SYNC=1

[ "${DISABLE_CLAIM_SYNC:-}" = "1" ] && exit 0

# Resolve LINEAR_API_KEY: env var → Infisical → skip
LINEAR_API_KEY="${LINEAR_API_KEY:-}"
if [ -z "$LINEAR_API_KEY" ] && command -v infisical >/dev/null 2>&1; then
  LINEAR_API_KEY=$(infisical secrets get LINEAR_API_KEY --plain 2>/dev/null || true)
fi
[ -z "$LINEAR_API_KEY" ] && exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
CLAIMS_DIR="$PROJECT_DIR/.claude/claims"
[ ! -d "$CLAIMS_DIR" ] && exit 0

NOW=$(date +%Y-%m-%dT%H:%M)

# Process each MEGA claim file (has "phases" key)
for claim_file in "$CLAIMS_DIR"/CAB-*.json; do
  [ ! -f "$claim_file" ] && continue

  # Skip standalone claims (no phases array)
  HAS_PHASES=$(jq -r 'has("phases")' "$claim_file" 2>/dev/null)
  [ "$HAS_PHASES" != "true" ] && continue

  UPDATED=false

  # Get number of phases
  PHASE_COUNT=$(jq '.phases | length' "$claim_file" 2>/dev/null)
  [ -z "$PHASE_COUNT" ] && continue

  for i in $(seq 0 $((PHASE_COUNT - 1))); do
    # Skip already completed phases
    COMPLETED=$(jq -r ".phases[$i].completed_at // empty" "$claim_file" 2>/dev/null)
    [ -n "$COMPLETED" ] && continue

    # Get tickets for this phase
    TICKETS=$(jq -r ".phases[$i].tickets[]" "$claim_file" 2>/dev/null)
    [ -z "$TICKETS" ] && continue

    # Check each ticket on Linear
    ALL_DONE=true
    for ticket in $TICKETS; do
      RESPONSE=$(curl -s --max-time 5 -X POST https://api.linear.app/graphql \
        -H "Authorization: $LINEAR_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"{ issues(filter: { identifier: { eq: \\\"$ticket\\\" } }) { nodes { state { type } } } }\"}" 2>/dev/null)

      STATE_TYPE=$(echo "$RESPONSE" | jq -r '.data.issues.nodes[0].state.type // empty' 2>/dev/null)

      if [ "$STATE_TYPE" != "completed" ]; then
        ALL_DONE=false
        break
      fi
    done

    # If all tickets Done → mark phase completed
    if [ "$ALL_DONE" = "true" ]; then
      TEMP=$(mktemp)
      jq ".phases[$i].completed_at = \"$NOW\" | .phases[$i].owner = null" "$claim_file" > "$TEMP" 2>/dev/null
      if [ $? -eq 0 ] && [ -s "$TEMP" ]; then
        mv "$TEMP" "$claim_file"
        PHASE_NAME=$(jq -r ".phases[$i].name" "$claim_file" 2>/dev/null)
        MEGA_ID=$(jq -r '.mega' "$claim_file" 2>/dev/null)
        echo "--- Claims: $MEGA_ID Phase $i ($PHASE_NAME) → completed (synced from Linear) ---"
        UPDATED=true
      else
        rm -f "$TEMP"
      fi
    fi
  done
done

exit 0
