# Multi-Device Access — SSH + Infisical + Cloudflare Access

> Runbook for setting up access to the STOA VPS fleet and Infisical from a new device.

## Architecture

```
Device (laptop/desktop)
  │
  ├── SSH (per-device Ed25519 key)
  │   └── VPS fleet (kong, gravitee, n8n, HEGEMON workers)
  │
  └── Infisical (per-device Machine Identity)
      └── Cloudflare Access (Service Token + email OTP)
          └── vault.gostoa.dev (Infisical self-hosted)
```

## Tier 1: SSH Access (new device)

### Step 1: Generate a device-specific SSH key

On the **new device**:

```bash
ssh-keygen -t ed25519 -C "stoa-laptop" -f ~/.ssh/id_ed25519_stoa_laptop
```

### Step 2: Distribute the public key

From a device that **already has access** (e.g., desktop):

```bash
# Distribute to all VPS in the fleet
./scripts/ops/distribute-ssh-key.sh ~/.ssh/id_ed25519_stoa_laptop.pub

# Verify
./scripts/ops/distribute-ssh-key.sh ~/.ssh/id_ed25519_stoa_laptop.pub --dry-run
```

### Step 3: Configure SSH on the new device

Add to `~/.ssh/config` on the new device:

```
# --- STOA VPS Fleet ---
Host kong-vps
  HostName 51.83.45.13
  User debian
  IdentityFile ~/.ssh/id_ed25519_stoa_laptop
  IdentitiesOnly yes

Host gravitee-vps
  HostName 54.36.209.237
  User debian
  IdentityFile ~/.ssh/id_ed25519_stoa_laptop
  IdentitiesOnly yes

Host n8n-vps
  HostName 51.254.139.205
  User debian
  IdentityFile ~/.ssh/id_ed25519_stoa_laptop
  IdentitiesOnly yes

# HEGEMON workers — add as provisioned
# Host hegemon-worker-1
#   HostName <IP>
#   User hegemon
#   IdentityFile ~/.ssh/id_ed25519_stoa_laptop
#   IdentitiesOnly yes
```

Also set the env var for scripts:

```bash
echo 'export STOA_SSH_KEY=~/.ssh/id_ed25519_stoa_laptop' >> ~/.zprofile
```

### Step 4: Test

```bash
ssh kong-vps uptime
ssh n8n-vps "docker ps --format '{{.Names}}'"
```

### Revoking a device

If a device is lost or decommissioned:

```bash
# From any device with access
./scripts/ops/distribute-ssh-key.sh --remove ~/.ssh/id_ed25519_stoa_<device>.pub
```

## Tier 2: Infisical Machine Identity (new device)

### Step 1: Create a new Machine Identity

1. Go to https://vault.gostoa.dev → **Organization Settings** → **Machine Identities**
2. Click **Create Identity**
3. Name: `stoa-cli-<device>` (e.g., `stoa-cli-laptop`)
4. Auth Method: **Universal Auth**
5. Access Token TTL: `86400` (24h)
6. Max TTL: `2592000` (30 days)
7. **Save** → Copy **Client ID** and **Client Secret**

### Step 2: Attach project role

1. Go to **Project** `stoa-infra` → **Settings** → **Access Control**
2. Add the new Machine Identity
3. Role: `admin` (or `member` if read-only is sufficient)

### Step 3: Store credentials on the new device

```bash
# Store Client Secret in macOS Keychain
security add-generic-password \
  -a "infisical-client-secret" \
  -s "infisical-client-secret" \
  -w "<CLIENT_SECRET>" \
  -U

# Add Client ID to shell profile
echo 'export INFISICAL_CLIENT_ID=<CLIENT_ID>' >> ~/.zprofile
```

### Step 4: Install helper scripts

Copy from desktop or clone from repo:

```bash
# infisical-token — fetches access token from Machine Identity
cp scripts/ops/infisical-token.sh ~/.local/bin/infisical-token
chmod +x ~/.local/bin/infisical-token

# Test
eval $(infisical-token)
echo $INFISICAL_TOKEN | cut -c1-20  # Should show JWT prefix
```

### Step 5: Init Infisical CLI

```bash
cd ~/hlfh-repos/stoa
infisical init --domain=https://vault.gostoa.dev/api
# Select project: stoa-infra
```

## Tier 3: Cloudflare Access (hardening)

### Why

Without Cloudflare Access, `vault.gostoa.dev` is accessible from any IP — only protected by auth credentials. Cloudflare Access adds:

- **Service Token auth** for scripts/CLI (header-based, no browser)
- **Email OTP** for browser access (humans)
- **Audit log** (who accessed when)
- **Session expiry** (24h)
- **DDoS protection** (Cloudflare proxy)

### Setup

```bash
# Requires CF_API_TOKEN with Zone:DNS:Edit + Access:Edit permissions
export CF_API_TOKEN="<token>"

# Preview
./scripts/ops/setup-cloudflare-access.sh --dry-run

# Execute
./scripts/ops/setup-cloudflare-access.sh
```

The script will:
1. Enable Cloudflare proxy on `vault.gostoa.dev` DNS record
2. Create an Access Application
3. Create a Service Token (`stoa-infisical-cli`)
4. Create Access Policies (service token + email)
5. Output `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET`

### Post-setup

1. **Store in Infisical** (before Access is enforced!):

```bash
infisical secrets set CF_ACCESS_CLIENT_ID=<id> --env=prod --path=/cloudflare
infisical secrets set CF_ACCESS_CLIENT_SECRET=<secret> --env=prod --path=/cloudflare
```

2. **Add to each device's shell profile** (`~/.zprofile`):

```bash
export CF_ACCESS_CLIENT_ID="<id>"
export CF_ACCESS_CLIENT_SECRET="<secret>"
```

3. **Add to each VPS** (`~/.env.hegemon`):

```bash
export CF_ACCESS_CLIENT_ID="<id>"
export CF_ACCESS_CLIENT_SECRET="<secret>"
```

4. **Verify**:

```bash
curl -sf \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  https://vault.gostoa.dev/api/status
```

### How scripts use it

All scripts source `scripts/ops/vps-inventory.sh` which reads `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` from env. The `infisical_curl` helper automatically adds CF headers when set.

**Backward compatible**: if the env vars are empty, no CF headers are sent. This means:
- Before Cloudflare Access is enabled: scripts work as before
- After Cloudflare Access is enabled: scripts work if env vars are set

### Rotating the Service Token

```bash
# 1. Delete old token in Cloudflare dashboard or via API
# 2. Re-run setup (creates a new token)
./scripts/ops/setup-cloudflare-access.sh

# 3. Update everywhere: Infisical, ~/.zprofile, VPS ~/.env.hegemon
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `403 Forbidden` on vault.gostoa.dev | CF Access blocking, missing headers | Set `CF_ACCESS_CLIENT_ID` + `CF_ACCESS_CLIENT_SECRET` |
| `403` with headers set | Service Token expired or revoked | Rotate token via setup script |
| Infisical UI shows CF login page | Expected — use email OTP to authenticate | Enter admin@gostoa.dev, check email for code |
| Scripts fail after enabling proxy | DNS propagation (up to 5 min) | Wait, then retry |
| `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` | Cloudflare SSL mode mismatch | Set SSL mode to "Full (strict)" in CF dashboard |

## Device Inventory

| Device | SSH Key | Machine Identity | CF Service Token |
|--------|---------|-----------------|-----------------|
| Desktop (iMac) | `id_ed25519_stoa` | `stoa-cli-desktop` | Shared `stoa-infisical-cli` |
| Laptop (MBP) | `id_ed25519_stoa_laptop` | `stoa-cli-laptop` | Shared `stoa-infisical-cli` |
| HEGEMON workers | Per-VPS deploy key | N/A (use curl + token) | Shared `stoa-infisical-cli` |
| GitHub Actions | N/A | N/A | Uses `INFISICAL_TOKEN` secret |

## Security Model

```
Layer 1: Network  — Cloudflare Access (Service Token or email OTP)
Layer 2: Auth     — Infisical Machine Identity (Client ID + Secret → JWT)
Layer 3: RBAC     — Infisical project role (admin/member)
Layer 4: Audit    — Cloudflare Access logs + Infisical audit logs
Layer 5: Rotation — Service Token (yearly), Machine Identity (90 days)
```

**Key principle**: 1 key per device, 1 identity per device, shared service token.
If a device is compromised: revoke its SSH key + delete its Machine Identity. Service Token stays valid for other devices.
