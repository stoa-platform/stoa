#!/usr/bin/env bash
# Start HEGEMON agent tmux session.
# Called by hegemon-agent.service (Type=simple, blocking).
set -euo pipefail

source "${HOME}/.env.hegemon"

SESSION="hegemon"
STOA_DIR="${HOME}/stoa"

# Ensure repo is up to date
cd "$STOA_DIR"
git checkout main 2>/dev/null
git pull --ff-only origin main 2>/dev/null || true

# Kill existing session if any
tmux -L hegemon kill-session -t "$SESSION" 2>/dev/null || true
sleep 1

# Create tmux session
tmux -L hegemon new-session -d -s "$SESSION" -x 200 -y 50

# Window 0: Agent (main work window)
tmux -L hegemon rename-window -t "${SESSION}:0" "AGENT"
tmux -L hegemon send-keys -t "${SESSION}:AGENT" "cd ${STOA_DIR} && source ~/.env.hegemon && export STOA_INSTANCE=\${HEGEMON_ROLE:-backend}" C-m

# Window 1: Monitor (htop + watchdog logs)
tmux -L hegemon new-window -t "${SESSION}" -n "MONITOR"
tmux -L hegemon send-keys -t "${SESSION}:MONITOR" "htop" C-m

echo "HEGEMON tmux session started: tmux -L hegemon attach -t ${SESSION}"

# BLOCK: keep the process alive so systemd (Type=simple) tracks the session.
# When the tmux session dies, this loop exits, and systemd restarts the service.
while tmux -L hegemon has-session -t "$SESSION" 2>/dev/null; do
  sleep 30
done
