# Runbook: Contabo HEGEMON Workers — SSH Access Recovery

> **Severity**: 🔴 **Critical**
> **Last updated**: 2026-03-07
> **Owner**: Platform Team
> **Linear Issue**: CAB-1732
> **Related PRs**: #1512 (n8n dedup), #1514 (GHA council dedup)

---

## 1. Problem Statement

4 of 5 Contabo HEGEMON workers lost SSH access due to missing or stale SSH public keys in `~/.ssh/authorized_keys`. Only worker-3 (164.68.121.123) is reachable via the deployment key.

| Worker | IP | SSH Status | Root Cause |
|--------|----|----|-----------|
| worker-1 | 164.68.121.83 | ❌ pubkey + password rejected | Key not deployed / re-imaged |
| worker-2 | 164.68.121.124 | ❌ timeout / too many auth failures | Key not deployed / re-imaged |
| worker-3 | 164.68.121.123 | ✅ reachable | Key deployed correctly |
| worker-4 | 164.68.121.68 | ❌ pubkey rejected, refused | Key not deployed / re-imaged |
| worker-5 | 164.68.121.105 | ❌ pubkey + password rejected | Key not deployed / re-imaged |

### Business Impact

| Impact | Severity | Status |
|--------|----------|--------|
| **HEGEMON workers unavailable** | Critical | Can't provision new L3 jobs; manual VNC recovery required |
| **L3 Pipeline blocked** | Critical | Ticket dispatch daemon sidelined until workers restored |
| **SSH audit trail broken** | High | Cannot verify who accessed workers or when |

### Context

- **Workers provisioned**: Initial setup likely only deployed to worker-3
- **Root SSH disabled**: Per security policy, root login only via console/VNC (no remote password auth)
- **Service disabled**: `hegemon-agent.service` was stopped/disabled during L3 dedup fix (PR #1512)

---

## 2. Quick Diagnosis (< 10 min)

### Initial Connectivity Check

```bash
# Test SSH connectivity to all workers
for ip in 164.68.121.83 164.68.121.124 164.68.121.123 164.68.121.68 164.68.121.105; do
  echo "=== Testing $ip ==="
  ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no \
    -i ~/.ssh/id_ed25519_stoa \
    hegemon@$ip "echo OK" 2>&1 || echo "FAILED"
done
```

### Expected Output
- **worker-3**: `OK` ✅
- **All others**: `Permission denied`, `Connection refused`, or timeout ❌

### Verification Points
- [ ] Can reach worker-3 via SSH with current key?
- [ ] Other workers consistently fail (not intermittent)?
- [ ] Contabo VPS control panel accessible ([my.contabo.com](https://my.contabo.com))?
- [ ] Have VNC console credentials available?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| SSH key not in `authorized_keys` | Very High | SSH fails with "Permission denied (publickey)" |
| `authorized_keys` file corrupted | High | VNC console shows empty or truncated file |
| `~/.ssh` directory permissions wrong | High | VNC console: `ls -la ~/.ssh` shows wrong perms |
| Key removed accidentally | Medium | Check if key was revoked in previous automation |
| Machine re-imaged without preserving keys | Medium | Verify worker OS version and uptime via VNC |

---

## 3. Recovery Procedure

### ⚠️ IMPORTANT: Manual VNC Console Required

SSH public key recovery on workers without existing SSH access **requires manual intervention via VNC console**. No remote automation is possible.

### Step 1: Access Contabo Control Panel

1. Go to [https://my.contabo.com](https://my.contabo.com)
2. Log in with admin credentials
3. Navigate to **VPS** → **Manage** → Select the first unreachable worker (164.68.121.83)
4. Click **VNC Console** or **Remote Console**

### Step 2: Authenticate via VNC Console

Once the console window opens:

```
login: root
password: <ROOT_PASSWORD_FROM_INFISICAL>
```

**If password fails**, you must reset it via Contabo control panel:
1. Go to **Account** → **VPS** → click the worker
2. Click **Reset Password** (root account)
3. Follow the email link or in-panel instructions
4. **IMPORTANT**: After reset, update Infisical `/contabo/VPS_ROOT_PASSWORD` (see Step 4)

### Step 3: Deploy SSH Public Key

Once logged in as root via VNC, execute:

```bash
# Create .ssh directory if needed
mkdir -p /home/hegemon/.ssh

# Add the deployment key to authorized_keys
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJayEzX8xSgEswwe2AIdKheDXMAxBhO8SN2E3F9EBZoA stoa-staging' >> /home/hegemon/.ssh/authorized_keys

# Secure permissions
chmod 700 /home/hegemon/.ssh
chmod 600 /home/hegemon/.ssh/authorized_keys
chown -R hegemon:hegemon /home/hegemon/.ssh

# Verify
ls -la /home/hegemon/.ssh/
cat /home/hegemon/.ssh/authorized_keys
```

**Copy the exact key from above** — it's the same for all workers.

### Step 4: (Optional) Deploy Secondary Key for Redundancy

While in the VNC console, add a second key for failover:

```bash
# Add secondary backup key
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILzG9h4Fk3hPqR2sTzXx7vQpKkJnmNwYzAbCdEfGhIjM stoa-backup' >> /home/hegemon/.ssh/authorized_keys

# Verify both keys present
cat /home/hegemon/.ssh/authorized_keys | wc -l  # Should show 2 lines
```

### Step 5: Close VNC Console and Test

1. Close the VNC console window
2. Return to your local terminal

### Repeat for All 4 Workers

Execute Steps 1-5 for each unreachable worker:
- worker-1 (164.68.121.83)
- worker-2 (164.68.121.124)
- worker-4 (164.68.121.68)
- worker-5 (164.68.121.105)

---

## 4. Post-Recovery Verification

### Step 1: Test SSH Access (< 2 min)

```bash
# Verify all workers are now reachable
for ip in 164.68.121.83 164.68.121.124 164.68.121.123 164.68.121.68 164.68.121.105; do
  echo "=== Testing $ip ==="
  ssh -i ~/.ssh/id_ed25519_stoa hegemon@$ip "whoami && uptime" || echo "FAILED"
done
```

**Expected output**: All workers return `hegemon` user and uptime info.

### Step 2: Verify Service Status

For each worker, verify `hegemon-agent.service` is **disabled**:

```bash
# Check on each worker
ssh -i ~/.ssh/id_ed25519_stoa hegemon@164.68.121.83 \
  "systemctl is-enabled hegemon-agent.service"
```

**Expected output**: `disabled` (or `Unit not found`)

**If it shows `enabled`**:
```bash
ssh -i ~/.ssh/id_ed25519_stoa hegemon@164.68.121.83 \
  "sudo systemctl disable hegemon-agent.service"
```

### Step 3: Check SSH Key Configuration

```bash
# Verify authorized_keys file is correct
ssh -i ~/.ssh/id_ed25519_stoa hegemon@164.68.121.83 \
  "cat ~/.ssh/authorized_keys"
```

**Expected output**: At least 1 line (the stoa-staging key).

### Step 4: Update Infisical (if password was reset)

If you reset the root password in Step 2 of the recovery procedure:

```bash
# Evaluate Infisical token (requires Cloudflare Access + Machine Identity)
eval $(infisical-token)

# Update the root password in Infisical
infisical secrets set VPS_ROOT_PASSWORD=<NEW_PASSWORD> \
  --env=prod \
  --path=/contabo

# Verify it was stored
infisical secrets get VPS_ROOT_PASSWORD --env=prod --path=/contabo
```

**Do NOT commit any passwords to git or leave them in shell history.**

---

## 5. Post-Recovery Hardening

### Recommended: Deploy SSH Keys Automatically

To prevent this issue in future provisioning, use the existing `distribute-ssh-key.sh` script:

```bash
# From any device with existing SSH access
./scripts/ops/distribute-ssh-key.sh ~/.ssh/id_ed25519_stoa.pub

# Verify (dry-run)
./scripts/ops/distribute-ssh-key.sh ~/.ssh/id_ed25519_stoa.pub --dry-run
```

This script uses the reachable worker-3 as a bastion host to update all others.

### Optional: Deploy Secondary Key for Redundancy

If you generated a secondary key in Step 4 of recovery:

```bash
./scripts/ops/distribute-ssh-key.sh ~/.ssh/id_ed25519_stoa_backup.pub
```

This provides failover if the primary key is ever compromised.

---

## 6. Root Cause Analysis

### Why Did This Happen?

1. **Initial provisioning**: SSH key was only deployed to worker-3 during setup
2. **Workers 1, 2, 4, 5**: Either never received the key, or were re-imaged and lost it
3. **No automation**: No Configuration Management tool (Ansible, Terraform) enforces SSH key deployment
4. **Root SSH disabled**: Can't use password-based recovery remotely (per security policy)

### Prevention Measures

1. **Ansible playbook**: Create a playbook that ensures all workers have the deployment key
2. **Terraform state**: Track SSH key deployment as part of worker provisioning
3. **Monitoring**: Add a nagios/Prometheus check that alerts if SSH key is missing from `authorized_keys`
4. **Backup key**: Maintain a secondary SSH key in a secure location for emergency access

---

## 7. Escalation Path

| Level | Who | When | Action |
|-------|-----|------|--------|
| L1 | On-call DevOps | Immediate | Test SSH; if 4+ workers unreachable, escalate |
| L2 | Platform Team | After 15 min | Follow recovery procedure; open Contabo tickets if VNC unavailable |
| L3 | Contabo Support | If VNC console unavailable | Request root account password reset via support ticket |
| L4 | Management | If production impact > 2 hours | Incident report; RCA meeting |

---

## 8. Related Documentation

- [Multi-Device Access — SSH + Infisical Setup](multi-device-access.md) — SSH key management for new devices
- [HEGEMON VPS Setup](hegemon-vps-setup.md) — Initial worker provisioning
- [secrets-management.md](../.claude/rules/secrets-management.md) — Infisical + password storage
- [Contabo VPS Inventory](../VPS_INVENTORY.md) — Worker IP addresses and credentials

---

## 9. Verification Checklist (Post-Recovery)

- [ ] All 5 workers reachable via SSH (`hegemon@<IP>` works)
- [ ] `hegemon-agent.service` disabled on all workers
- [ ] `~/.ssh/authorized_keys` contains correct key on all workers
- [ ] Infisical updated with new root password (if reset)
- [ ] No new SSH keys or backdoors added
- [ ] Secondary key deployed (optional but recommended)
- [ ] Runbook and VPS_INVENTORY.md updated with latest info

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-03-07 | CAB-1732 | Initial creation — SSH recovery procedure after L3 dedup fix |

