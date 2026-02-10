# SOPS Encrypted Secrets

This directory contains SOPS-encrypted secrets for deployment.

## Setup

1. Install age and sops:
   ```bash
   brew install age sops
   ```

2. Generate an age keypair:
   ```bash
   age-keygen -o ~/.config/sops/age/keys.txt
   ```

3. Update `.sops.yaml` at repo root with your age public key.

4. Add the private key to GitHub Actions:
   - Settings > Secrets > `SOPS_AGE_KEY` = contents of `keys.txt`

## Usage

### Encrypt a new secret
```bash
sops -e secrets.yaml > deploy/secrets/production.enc.yaml
```

### Decrypt locally
```bash
sops -d deploy/secrets/production.enc.yaml
```

### Deploy to cluster
```bash
./scripts/deploy-secrets.sh production
```

## File naming convention
- `*.enc.yaml` — SOPS-encrypted YAML (committed to git)
- Never commit unencrypted secrets
