#!/usr/bin/env bash
# Verify HEGEMON VPS worker is fully operational.
# Run from local machine after setup-base.sh + setup-claude.sh.
#
# Usage: ./verify.sh <VPS_IP> [SSH_KEY]
set -euo pipefail

VPS_IP="${1:?Usage: ./verify.sh <VPS_IP> [SSH_KEY]}"
SSH_KEY="${2:-$HOME/.ssh/id_ed25519_stoa}"
HEGEMON_USER="hegemon"
PASS=0
FAIL=0

ssh_cmd() {
  ssh -i "$SSH_KEY" -o ConnectTimeout=10 "${HEGEMON_USER}@${VPS_IP}" "$@"
}

check() {
  local label="$1"
  shift
  if ssh_cmd "$@" &>/dev/null; then
    echo "  [PASS] ${label}"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] ${label}"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== HEGEMON Verification: ${VPS_IP} ==="
echo ""

# System checks
echo "[System]"
check "SSH access"         "whoami"
check "Sudo access"        "sudo -n echo OK"
check "Swap active"        "swapon --show | grep -q swapfile"
check "UFW active"         "sudo ufw status | grep -q active"
check "fail2ban running"   "systemctl is-active fail2ban"

# Tools
echo ""
echo "[Tools]"
check "Claude CLI"         "claude --version"
check "Node.js 20"         "node --version | grep -q v20"
check "Git"                "git --version"
check "tmux"               "tmux -V"
check "jq"                 "jq --version"
check "curl"               "curl --version | head -1"

# Repo
echo ""
echo "[Repository]"
check "Stoa cloned"        "test -d ~/stoa/.git"
check "Git remote"         "cd ~/stoa && git remote -v | grep -q stoa-platform"
check "Git user config"    "git config --global user.email | grep -q hegemon"

# Memory protection
echo ""
echo "[Memory Protection]"
check "Watchdog service"   "systemctl --user is-active claude-watchdog"
check "claude-limited"     "test -x ~/.local/bin/claude-limited"

# Environment
echo ""
echo "[Environment]"
check "env.hegemon exists" "test -f ~/.env.hegemon"
check "ANTHROPIC_API_KEY"  "source ~/.env.hegemon && test -n \"\$ANTHROPIC_API_KEY\""

# Claude Code functional test
echo ""
echo "[Functional]"
check "Claude headless"    "source ~/.env.hegemon && claude -p 'echo 42' --output-format json 2>/dev/null | grep -q '42'"

# Git push test (create + delete ephemeral branch)
echo ""
echo "[Git Push]"
PUSH_OK=$(ssh_cmd 'cd ~/stoa && \
  git checkout main && git pull --ff-only 2>/dev/null && \
  TESTBRANCH="test-verify-$(hostname)-$(date +%s)" && \
  git checkout -b "$TESTBRANCH" && \
  git commit --allow-empty -m "test: verify push from $(hostname)" && \
  git push origin "$TESTBRANCH" 2>/dev/null && \
  git checkout main && \
  git branch -D "$TESTBRANCH" && \
  git push origin --delete "$TESTBRANCH" 2>/dev/null && \
  echo PUSH_OK' 2>/dev/null)
if echo "$PUSH_OK" | grep -q "PUSH_OK"; then
  echo "  [PASS] Git push + delete"
  PASS=$((PASS + 1))
else
  echo "  [FAIL] Git push + delete"
  FAIL=$((FAIL + 1))
fi

# Summary
echo ""
TOTAL=$((PASS + FAIL))
echo "=== Results: ${PASS}/${TOTAL} passed ==="
if [ "$FAIL" -eq 0 ]; then
  echo "  All checks passed. VPS worker is ready."
  exit 0
else
  echo "  ${FAIL} check(s) failed. Review and fix before using."
  exit 1
fi
