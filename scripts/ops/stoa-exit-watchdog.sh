#!/usr/bin/env bash
# stoa-exit-watchdog — Clears /exit poisoning from Claude Code TUI input buffers.
#
# Problem: Auto-compact at low context injects `/exit` into the TUI input buffer.
#          Cross-pane `tmux send-keys Enter` then fires it, killing the session.
#
# Solution: Monitor all Claude panes every 5s. If the capture buffer contains `/exit`
#           at a prompt boundary (not in output), send Ctrl-U to clear the line.
#
# Usage: Launched by stoa-parallel in the MONITOR pane.
#   stoa-exit-watchdog.sh <session-name> <pane-list>
#   stoa-exit-watchdog.sh stoa "2 3 4 5 6"

set -euo pipefail

SESSION="${1:-stoa}"
PANES="${2:-2 3 4 5 6}"
INTERVAL="${3:-5}"

log() {
  echo "[$(date +%H:%M:%S)] watchdog: $*"
}

log "Starting /exit watchdog for session=$SESSION panes=($PANES) interval=${INTERVAL}s"

while true; do
  for pane in $PANES; do
    # Capture last 3 lines of the pane buffer
    captured=$(tmux capture-pane -t "${SESSION}:0.${pane}" -p -S -3 2>/dev/null || true)

    # Detect /exit at a prompt boundary:
    #   - Line starts with /exit (user input line)
    #   - Line ends with /exit (after prompt marker like "> ")
    #   - /exit preceded by prompt chars (>, $, %)
    # Exclude /exit appearing in command output (e.g., grep results, help text)
    if echo "$captured" | grep -qE '(^|\$ |> |% )/exit\s*$'; then
      log "CLEARING /exit poisoning in pane $pane"
      # Ctrl-U clears the current input line without executing
      tmux send-keys -t "${SESSION}:0.${pane}" C-u 2>/dev/null || true
      # Small delay to ensure the clear takes effect
      sleep 0.2
      # Verify it was cleared
      recaptured=$(tmux capture-pane -t "${SESSION}:0.${pane}" -p -S -1 2>/dev/null || true)
      if echo "$recaptured" | grep -qE '(^|\$ |> |% )/exit\s*$'; then
        log "WARNING: /exit still present in pane $pane after Ctrl-U, sending Backspace×5"
        tmux send-keys -t "${SESSION}:0.${pane}" BSpace BSpace BSpace BSpace BSpace 2>/dev/null || true
      fi
    fi
  done
  sleep "$INTERVAL"
done
