#!/usr/bin/env bash
# cron-token-metrics.sh — Batch token metrics collection (replaces per-session Stop hooks)
#
# Runs hourly via VPS cron. Calls the same scripts that were previously in the
# Stop hook chain, but aggregated instead of per-session.
#
# Install on VPS:
#   crontab -e
#   0 * * * * /opt/stoa/deploy/vps/monitoring/cron-token-metrics.sh >> /var/log/stoa-metrics.log 2>&1
#
# Required env vars (set in crontab or /etc/environment):
#   CLAUDE_PROJECT_DIR  — path to stoa repo clone on VPS
#   PUSHGATEWAY_URL     — e.g. https://pushgateway.gostoa.dev
#
# Optional:
#   HEGEMON_INGEST_KEY  — API key for trace ingestion
#   HEGEMON_STATE_DB    — path to state.db

set -euo pipefail

CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/opt/stoa}"
export CLAUDE_PROJECT_DIR

echo "[$(date -u +%Y-%m-%dT%H:%M)] Starting token metrics collection..."

# 1. Cost tracker — parse stats-cache.json, push to Pushgateway
if [ -f "$CLAUDE_PROJECT_DIR/.claude/hooks/stop-cost-tracker.sh" ]; then
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/stop-cost-tracker.sh" || true
fi

# 2. HEGEMON trace — push session data to Console dashboard
if [ -f "$CLAUDE_PROJECT_DIR/.claude/hooks/stop-hegemon-trace.sh" ]; then
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/stop-hegemon-trace.sh" || true
fi

echo "[$(date -u +%Y-%m-%dT%H:%M)] Token metrics collection complete."
