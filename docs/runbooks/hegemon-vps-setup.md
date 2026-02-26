# HEGEMON VPS Setup — Reproducible Guide

> **Ticket**: CAB-1518 (parent: CAB-1514)
> **Last updated**: 2026-02-26
> **Audience**: Ops team, automated provisioning pipeline

## Prerequisites

| Requirement | Source |
|-------------|--------|
| OVH API credentials | Infisical `/ovh` (APPLICATION_KEY, APPLICATION_SECRET, CONSUMER_KEY) |
| SSH key | `~/.ssh/id_ed25519_stoa` (or specify alternate) |
| GitHub deploy key | Generated during setup, must be added to repo settings |
| Anthropic API key | Infisical `/anthropic/ANTHROPIC_API_KEY` |
| Slack webhook | Infisical `/slack/SLACK_WEBHOOK_URL` |

## Step-by-Step Setup

### Step 1: Order VPS on OVH Manager

1. Go to [OVH Manager](https://www.ovh.com/manager/#/dedicated/vps)
2. Order: **VPS 2026 gen — VPS-1** (4 vCPU, 8 GB RAM, 75 GB NVMe)
3. Datacenter: **GRA** (Gravelines, France)
4. OS: **Debian 12 (Bookworm)**
5. SSH key: paste your `~/.ssh/id_ed25519_stoa.pub`
6. Note the assigned IP address

```bash
export VPS_IP=<new-vps-ip>
```

### Step 2: Run Base Setup

Installs packages, creates `hegemon` user, hardens SSH, configures firewall, creates swap.

```bash
./deploy/vps/hegemon/setup-base.sh $VPS_IP
```

**What it does** (6 steps):
1. Creates `hegemon` user with NOPASSWD sudo
2. Copies SSH authorized_keys from root
3. Disables root SSH login
4. Installs: tmux, git, curl, jq, wget, fail2ban, ufw, htop, build-essential
5. Configures UFW (SSH only)
6. Creates 4 GB swap (swappiness=10)

**Verify**:
```bash
ssh -i ~/.ssh/id_ed25519_stoa hegemon@$VPS_IP 'whoami && sudo -n echo OK && tmux -V'
```

### Step 3: Run Claude Code Setup

Installs Claude Code CLI, Node.js, git deploy key, environment template, memory watchdog.

```bash
./deploy/vps/hegemon/setup-claude.sh $VPS_IP
```

**What it does** (6 steps):
1. Installs Claude Code CLI (native binary via `claude.ai/install.sh`)
2. Installs Node.js 20 (for MCP servers)
3. Generates ed25519 deploy key — **pause: add to GitHub repo settings**
4. Clones `stoa` repo to `~/stoa`
5. Creates `~/.env.hegemon` template (fill secrets manually)
6. Installs memory watchdog (systemd user service, 7 GB threshold) + cgroup wrapper

**Interactive step**: Script pauses at step 3 and displays the deploy key. You must:
1. Copy the displayed public key
2. Go to GitHub > `stoa-platform/stoa` > Settings > Deploy Keys
3. Add key with **write access** enabled
4. Press Enter to continue

### Step 4: Fill Secrets

SSH into the VPS and fill the environment file:

```bash
ssh -i ~/.ssh/id_ed25519_stoa hegemon@$VPS_IP
```

Edit `~/.env.hegemon`:
```bash
vim ~/.env.hegemon
```

Required values (from Infisical):
```bash
export ANTHROPIC_API_KEY="sk-ant-..."     # /anthropic/ANTHROPIC_API_KEY
export SLACK_WEBHOOK_URL="https://..."     # /slack/SLACK_WEBHOOK_URL
export POCKETBASE_URL="https://state.gostoa.dev"
export HEGEMON_ROLE="worker-1"
export HEGEMON_HOSTNAME="$(hostname)"
```

Source the env:
```bash
source ~/.env.hegemon
```

### Step 5: Verify Claude Code

```bash
# Basic test
claude --version

# Headless test
claude -p 'What is 2+2?' --output-format json

# Repo access test
cd ~/stoa && git fetch && git status
```

### Step 6: Verify Git Push

```bash
cd ~/stoa
git checkout -b test-hegemon-$(hostname)
echo "# test" > /tmp/test-hegemon.md
git add /tmp/test-hegemon.md 2>/dev/null || true
git commit --allow-empty -m "test: verify hegemon push from $(hostname)"
git push origin HEAD
# Clean up
git checkout main && git branch -D test-hegemon-$(hostname)
git push origin --delete test-hegemon-$(hostname)
```

### Step 7: Verify Watchdog

```bash
# Check watchdog is running
systemctl --user status claude-watchdog

# Check logs
tail -f ~/.local/log/claude-watchdog.log

# Test cgroup wrapper
claude-limited --version
```

### Step 8: Test Slack Notification (optional)

```bash
curl -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d "{\"text\": \"HEGEMON $(hostname): setup complete\"}"
```

## Post-Setup Checklist

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | SSH as hegemon | `ssh hegemon@$VPS_IP` | Login success |
| 2 | Root login disabled | `ssh root@$VPS_IP` | Permission denied |
| 3 | Swap active | `swapon --show` | 4G swapfile |
| 4 | UFW active | `sudo ufw status` | SSH allowed |
| 5 | Claude installed | `claude --version` | Version string |
| 6 | Node installed | `node --version` | v20.x.x |
| 7 | Git clone OK | `cd ~/stoa && git status` | On branch main |
| 8 | Git push OK | Test branch push/delete | Success |
| 9 | Watchdog running | `systemctl --user status claude-watchdog` | active (running) |
| 10 | Env vars set | `env \| grep ANTHROPIC` | Key present |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `claude: command not found` | PATH not set | `source ~/.bashrc` or add `~/.local/bin` to PATH |
| Git push rejected | Deploy key not added or no write access | Check GitHub repo Settings > Deploy Keys |
| Watchdog not starting | Lingering login required | `loginctl enable-linger hegemon` |
| Claude OOM killed | Memory leak (issue #21403) | Use `claude-limited` wrapper, check watchdog logs |
| Node.js missing | nodesource repo not added | Re-run setup-claude.sh step 2 |
| SSH timeout | UFW blocking | Check `sudo ufw status`, ensure SSH allowed |

## Architecture

```
Local Machine (macOS)
  │
  ├── setup-base.sh ──→ [SSH root@VPS] Base OS, user, firewall, swap
  │
  └── setup-claude.sh ──→ [SSH hegemon@VPS] Claude CLI, Node, git, watchdog
                              │
                              └── VPS (Debian 12, OVH GRA)
                                    ├── ~/stoa (git repo)
                                    ├── ~/.env.hegemon (secrets)
                                    ├── ~/.local/bin/claude (CLI)
                                    ├── ~/.local/bin/claude-watchdog.sh (7GB kill)
                                    ├── ~/.local/bin/claude-limited (6GB cgroup)
                                    └── systemd user: claude-watchdog.service
```
