#!/usr/bin/env bash
# Start HEGEMON agent tmux session + auto-launch Claude Code.
# Called by hegemon-agent.service (Type=simple, blocking).
#
# What this script does:
#   1. Git pull latest code
#   2. Ensure ~/.claude.json has onboarding bypass (no interactive wizard)
#   3. Create tmux session (AGENT + MONITOR windows)
#   4. Auto-launch Claude Code in AGENT pane
#   5. Auto-approve MCP servers prompt (background watcher)
#   6. Block forever so systemd tracks the session
#
# Env vars (from ~/.env.hegemon):
#   HEGEMON_ROLE       — instance role (backend, frontend, mcp, auth, qa)
#   ANTHROPIC_API_KEY  — API key for Claude Code
#   SLACK_WEBHOOK_URL  — (optional) Slack notifications
#   GH_TOKEN           — GitHub token for gh CLI
set -euo pipefail

source "${HOME}/.env.hegemon"

SESSION="hegemon"
STOA_DIR="${HOME}/stoa"
ROLE="${HEGEMON_ROLE:-backend}"
LOG_TAG="[hegemon-start]"

log() { echo "${LOG_TAG} $(date '+%H:%M:%S') $*"; }

# ─── 1. Git pull ────────────────────────────────────────────────────────────
cd "$STOA_DIR"
git checkout main 2>/dev/null || true
git pull --ff-only origin main 2>/dev/null || true
log "Git updated: $(git log --oneline -1)"

# ─── 2. Ensure Claude config (idempotent) ───────────────────────────────────
ensure_claude_config() {
  python3 << 'PYEOF'
import json, os, subprocess

stoa_dir = os.environ.get("STOA_DIR", os.path.expanduser("~/stoa"))
api_key = os.environ.get("ANTHROPIC_API_KEY", "")
key_tail = api_key[-20:] if api_key else ""

# --- Patch ~/.claude.json (onboarding bypass + API key approval) ---
path = os.path.expanduser("~/.claude.json")
try:
    with open(path) as f:
        cfg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}

changed = False

# Onboarding bypass
if not cfg.get("hasCompletedOnboarding"):
    cfg["hasCompletedOnboarding"] = True
    changed = True

# Get installed Claude version
try:
    ver = subprocess.check_output(
        ["claude", "--version"], text=True, stderr=subprocess.DEVNULL
    ).strip().split()[-1]
except Exception:
    ver = "2.1.61"

if cfg.get("lastOnboardingVersion") != ver:
    cfg["lastOnboardingVersion"] = ver
    changed = True

# API key approval (last 20 chars)
approved = cfg.setdefault("customApiKeyResponses", {}).setdefault("approved", [])
if key_tail and key_tail not in approved:
    approved.append(key_tail)
    changed = True

# Project trust + tool permissions
proj = cfg.setdefault("projects", {}).setdefault(stoa_dir, {})
if not proj.get("hasTrustDialogAccepted"):
    proj["hasTrustDialogAccepted"] = True
    changed = True
expected_tools = [
    "Bash(*)", "Read", "Write", "Edit", "Glob", "Grep",
    "Agent", "WebFetch", "WebSearch"
]
if proj.get("allowedTools") != expected_tools:
    proj["allowedTools"] = expected_tools
    changed = True

if changed:
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[hegemon-start] Config patched: {path}")
else:
    print(f"[hegemon-start] Config OK (no changes)")

# --- Ensure ~/.claude/ directory exists ---
claude_dir = os.path.expanduser("~/.claude")
os.makedirs(claude_dir, exist_ok=True)

# --- Create ~/.claude/settings.json (global permissions for headless mode) ---
# acceptEdits mode only auto-approves file tools, NOT Bash commands.
# Solution: use default mode + comprehensive permissions.allow in settings.json.
# skipDangerousModePermissionPrompt prevents the "dangerous mode" warning.
settings_path = os.path.join(claude_dir, "settings.json")
expected_settings = {
    "permissions": {
        "allow": [
            "Bash(*)",
            "mcp__context7__resolve-library-id",
            "mcp__context7__query-docs",
            "mcp__playwright__*",
            "mcp__linear__*"
        ],
        "deny": []
    },
    "model": "opus",
    "skipDangerousModePermissionPrompt": True
}

settings_changed = False
try:
    with open(settings_path) as f:
        current = json.load(f)
    if (current.get("permissions") != expected_settings["permissions"]
            or not current.get("skipDangerousModePermissionPrompt")):
        settings_changed = True
except (FileNotFoundError, json.JSONDecodeError):
    settings_changed = True

if settings_changed:
    with open(settings_path, "w") as f:
        json.dump(expected_settings, f, indent=2)
    print(f"[hegemon-start] Settings patched: {settings_path}")
else:
    print(f"[hegemon-start] Settings OK (no changes)")
PYEOF
}

export STOA_DIR
ensure_claude_config
log "Claude config ensured"

# ─── 3. Create tmux session ─────────────────────────────────────────────────
tmux -L hegemon kill-session -t "$SESSION" 2>/dev/null || true
sleep 1

tmux -L hegemon new-session -d -s "$SESSION" -x 200 -y 50

# Window 0: AGENT (Claude Code runs here)
tmux -L hegemon rename-window -t "${SESSION}:0" "AGENT"

# Window 1: MONITOR (htop)
tmux -L hegemon new-window -t "${SESSION}" -n "MONITOR"
tmux -L hegemon send-keys -t "${SESSION}:MONITOR" "htop" C-m

log "tmux session created"

# ─── 4. Launch Claude Code in AGENT pane ─────────────────────────────────────
PROMPT="Worker ${ROLE^^}: lis memory.md et plan.md, cherche tickets instance:${ROLE} sur Linear, travaille sur le premier disponible."

tmux -L hegemon send-keys -t "${SESSION}:AGENT" \
  "export PATH=${HOME}/.local/bin:\$PATH && source ~/.env.hegemon && export STOA_INSTANCE=${ROLE} && cd ${STOA_DIR} && claude --permission-mode acceptEdits \"${PROMPT}\"" C-m

log "Claude Code launched: role=${ROLE}, mode=acceptEdits + settings.json permissions"

# ─── 5. Auto-approve MCP servers prompt (background) ────────────────────────
# Claude Code shows "Enter to confirm" when new MCP servers are found in .mcp.json.
# This watcher polls the tmux pane and sends Enter automatically.
(
  for i in $(seq 1 30); do
    sleep 2
    content=$(tmux -L hegemon capture-pane -t "${SESSION}:AGENT" -p 2>/dev/null || true)

    # MCP approval prompt detected — send Enter
    if echo "$content" | grep -q "Enter to confirm"; then
      sleep 1  # brief pause for UI stability
      tmux -L hegemon send-keys -t "${SESSION}:AGENT" Enter
      log "MCP servers auto-approved"
      break
    fi

    # Claude already past the prompt (thinking/reading/working)
    if echo "$content" | grep -qE "thinking|Recalling|Reading|Photosyn|Roosting|Shimmy|Discombo|Embellish"; then
      log "Claude started successfully (no MCP prompt)"
      break
    fi
  done
) &
MCP_WATCHER_PID=$!

log "HEGEMON agent ready: role=${ROLE}, pid=$$, mcp_watcher=${MCP_WATCHER_PID}"
log "Attach: tmux -L hegemon attach -t ${SESSION}"

# ─── 6. Block: keep process alive for systemd ───────────────────────────────
# When the tmux session dies, this loop exits, and systemd restarts the service.
while tmux -L hegemon has-session -t "$SESSION" 2>/dev/null; do
  sleep 30
done

log "tmux session ended — systemd will restart"
