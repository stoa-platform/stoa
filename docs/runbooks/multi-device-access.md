# Multi-Device Access — SSH + OpenBao Tooling Access

> Runbook for setting up access to the STOA VPS fleet and to the tooling secrets
> (OpenBao) from a new device. Infisical and its Cloudflare Access layer were
> retired by ADR-075 (2026-11-07).

## Architecture

```
Device (laptop/desktop)
  │
  ├── SSH (per-device Ed25519 key)
  │   └── VPS fleet (kong, gravitee, n8n, HEGEMON workers)
  │
  └── SSH tunnel (launchd com.stoa.openbao-tunnel) → https://127.0.0.1:18200
      └── OpenBao (dedicated VM) — read-only tooling token, secret/stoa/tooling/*
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
  HostName <KONG_VPS_IP>
  User debian
  IdentityFile ~/.ssh/id_ed25519_stoa_laptop
  IdentitiesOnly yes

Host gravitee-vps
  HostName <GRAVITEE_VPS_IP>
  User debian
  IdentityFile ~/.ssh/id_ed25519_stoa_laptop
  IdentitiesOnly yes

Host n8n-vps
  HostName <N8N_VPS_IP>
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

## Tier 2: OpenBao Tooling Access (new device)

Repository tooling (Claude hooks, `scripts/council-review.sh`,
`scripts/parallel/stoa-parallel`, operator scripts) reads secrets from OpenBao
through `scripts/lib/stoa-secret.sh`. OpenBao has no public URL. The platform
owner provides three things per device:

| Item | Default | Override |
|------|---------|----------|
| Tunnel to the OpenBao API (macOS: launchd `com.stoa.openbao-tunnel`) | `https://127.0.0.1:18200` | `STOA_OPENBAO_ADDR` |
| Private CA certificate | `~/.config/stoa/openbao-ca.pem` | `STOA_OPENBAO_CACERT` |
| Read-only periodic tooling token | macOS Keychain, service `stoa-openbao`, account `tooling`; Linux: `~/.config/stoa/openbao-tooling-token` (mode 600) | `STOA_OPENBAO_TOKEN`, `STOA_OPENBAO_KEYCHAIN_SERVICE` |

The token can only read `secret/stoa/tooling/*`. The helper renews it at most once
a day (stamp in `~/.cache/stoa`); an expired token makes reads fail with HTTP 403,
and the owner then issues a new one. Writes go through the owner's put-secret
tool, never through repository tooling.

Check the setup without printing the value:

```bash
v=$(scripts/lib/stoa-secret.sh anthropic ANTHROPIC_API_KEY) && echo "ok, ${#v} chars"; unset v
```

| Symptom (one line on stderr) | Cause | Fix |
|------------------------------|-------|-----|
| `OpenBao unreachable ... connection refused` | Tunnel down | Reload the launchd tunnel (or open it by hand) |
| `TLS verification failed` | Wrong or missing CA file | Install the CA at `~/.config/stoa/openbao-ca.pem` |
| `no OpenBao token` | No env var, Keychain item or token file | Ask the owner for a tooling token |
| `HTTP 403` | Token expired or path outside `stoa/tooling` | Ask the owner to reissue the token |
| `HTTP 404` / `field ... not found` | Secret not populated yet | Owner stores it with put-secret |

## Device Inventory

| Device | SSH Key | Tooling token |
|--------|---------|---------------|
| Desktop (iMac) | `id_ed25519_stoa` | Keychain `stoa-openbao` / `tooling` |
| Laptop (MBP) | `id_ed25519_stoa_laptop` | Keychain `stoa-openbao` / `tooling` |
| HEGEMON workers | Per-VPS deploy key | Token file, only if the host runs tooling |
| GitHub Actions | N/A | N/A (GitHub secrets) |

## Security Model

```
Layer 1: Network  — SSH tunnel only, no public endpoint
Layer 2: TLS      — private CA trusted per device (STOA_OPENBAO_CACERT)
Layer 3: Auth     — read-only periodic token scoped to secret/stoa/tooling/*
Layer 4: Handling — token sent as a header on curl's stdin, never in argv or logs
Layer 5: Rotation — renew-self at most once a day; the owner reissues on expiry
```

**Key principle**: 1 SSH key per device; tooling can read, never write.
If a device is compromised: revoke its SSH key and ask the owner to revoke and reissue the tooling token.
