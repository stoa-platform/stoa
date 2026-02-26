# HEGEMON VPS Worker — Quick Reference

> VPS-based AI Factory worker nodes running Claude Code CLI natively.

## Scripts

| Script | Run as | Purpose |
|--------|--------|---------|
| `provision.sh` | Local | OVH API info + manual ordering guide |
| `setup-base.sh <IP>` | Local → root@VPS | OS hardening, packages, swap |
| `setup-claude.sh <IP>` | Local → hegemon@VPS | Claude CLI, Node, git, watchdog |
| `setup-state.sh <IP>` | Local → hegemon@VPS | heg-state, PocketBase, Slack, agent service |
| `verify.sh <IP>` | Local | 18-point post-setup validation |
| `notify.sh` | VPS (source) | Slack notification functions |
| `hegemon-start.sh` | VPS (systemd) | tmux session initialization |
| `hegemon-agent.service` | VPS (systemd) | Auto-start agent on boot |

## Quick Setup

```bash
# 1. Order VPS on OVH Manager (VPS-1, Debian 12, GRA)
# 2. Run setup (3 scripts, in order)
export VPS_IP=<ip>
./deploy/vps/hegemon/setup-base.sh $VPS_IP
./deploy/vps/hegemon/setup-claude.sh $VPS_IP
./deploy/vps/hegemon/setup-state.sh $VPS_IP

# 3. Fill secrets on VPS
ssh hegemon@$VPS_IP
vim ~/.env.hegemon  # ANTHROPIC_API_KEY, SLACK_WEBHOOK_URL, HEGEMON_REMOTE_PASSWORD

# 4. Verify (18 automated checks)
./deploy/vps/hegemon/verify.sh $VPS_IP

# 5. Start agent
ssh hegemon@$VPS_IP 'sudo systemctl start hegemon-agent'
ssh hegemon@$VPS_IP 'tmux -L hegemon attach -t hegemon'
```

## Spec

- **VPS**: OVH VPS-1 (4 vCPU, 8 GB RAM, 75 GB NVMe) — EUR 4.49/mo
- **OS**: Debian 12 (Bookworm)
- **User**: `hegemon` (sudo NOPASSWD)
- **Firewall**: UFW (SSH only)
- **Swap**: 4 GB (swappiness=10)

## Memory Protection

| Layer | Tool | Threshold |
|-------|------|-----------|
| Swap | `/swapfile` | 4 GB |
| Watchdog | `claude-watchdog.service` | 7 GB RSS → kill |
| cgroup | `claude-limited` wrapper | 6 GB MemoryMax |
| Rotation | Session timeout | 45 min max |

## Runbooks

- [Cost Analysis](../../docs/runbooks/hegemon-cost-analysis.md)
- [Full Setup Guide](../../docs/runbooks/hegemon-vps-setup.md)
