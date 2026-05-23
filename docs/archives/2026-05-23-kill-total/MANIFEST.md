# Phase 1 Backup Manifest — STOA Shutdown 2026-05-23

**Date generated**: 2026-05-23T11:07:43Z
**Operator**: christophe.ab.cab.i@gmail.com (solo project mode)
**GPG recipient**: `8C31758A93F3B54D` (Christophe ABOULICAM <christophe.ab@icloud.com>)
**Local backup root**: `~/Backups/stoa-shutdown/` (gitignored, NEVER commit)
**This file**: pointer + manifest in git, content stays local-only

## Archives (9 files,  73M total)

| # | File | Source | Size (.gpg) | SHA-256 |
|---|------|--------|-------------|---------|
| 1 | `critical-keys/git-crypt-stoa-repo-local-2026-05-23.key.gpg` | stoa monorepo .git/git-crypt/keys/default (148 bytes) | 776 B | `ee1f4adf255210e1893dc99d6f661b7f50dd7b7b7e0f97e4b574881f4b511d25` |
| 2 | `critical-keys/git-crypt-vault-2026-05-23.key.gpg` | hcvault stoa/secrets/git-crypt (raw 228 bytes) | 769 B | `4ee6987594b4f1ba617ae8433508e9bb363bb9e2d7f4bd0b8502dc02331bcf3d` |
| 3 | `db/pg-stoa-incluster-2026-05-23.dump.gpg` | kubectl exec control-plane-db-0 pg_dump -Fc (in-cluster, 507 MB raw) | 64979905 B | `e3221a8aee046521e0fba1191d250162608765188f95ec713a206885fe371eca` |
| 4 | `hegemon/hegemon-w1-2026-05-23.tar.gz.gpg` | ssh hegemon@<contabo-w1> tar /opt/stoa-ops + ~/.hegemon + ~/.claude + units | 7636928 B | `7227458bfbac5b682431b1c1e561565282ec4edf5cac3756123c6ee2909f2be4` |
| 5 | `keycloak-realms-2026-05-23.tar.gz.gpg` | kcadm partial-export x7 realms (master+stoa+demos+IdPs) | 62038 B | `f4e170789a17c05297cc1cda5881eb3ac98015f082d9ca9abf17063ab5433b75` |
| 6 | `repos/stoa-infra-mirror-2026-05-23.tar.gz.gpg` | git clone --mirror PotoMitan/stoa-infra (5515 obj, 91 refs) | 1669918 B | `e0479e5f5f70a63e3510354f9c2a763609455d533d44dff8d439d0b996dd89aa` |
| 7 | `repos/stoa-strategy-mirror-2026-05-23.tar.gz.gpg` | git clone --mirror PotoMitan/stoa-strategy (146 obj) | 1710882 B | `10c8bf8c24a4414dc9a7848aec89173638e1a35bd08a14dc2b18966d98c132d9` |
| 8 | `ssh-keys-2026-05-23.tar.gz.gpg` | ~/.ssh/ (id_ed25519_stoa, _ovh, gitlab_stoa, config snapshot) | 10833 B | `7c598d1cc4cf6b89734bcf741e4b3f3ac8edc0c87deceb1208cd2849e7a40830` |
| 9 | `vault/hcvault-dump-2026-05-23.json.gpg` | hcvault.gostoa.dev (21 secrets KV stoa/* + secret/e2e/*) | 3536 B | `0eccef285fd76e0cc54d4a13dd4738f0db6f70012abb83878b574ac47b1d71f5` |

## Restore procedures

### Generic decrypt
```bash
gpg --decrypt ARCHIVE.gpg > ARCHIVE_CLEAR
# Prompts for passphrase via pinentry-mac
```

### Vault dump → restore to fresh Vault
```bash
gpg --decrypt hcvault-dump-2026-05-23.json.gpg | jq -c '.[]' | while read e; do
  mount=$(echo "$e" | jq -r '.mount')
  path=$(echo "$e" | jq -r '.path')
  data=$(echo "$e" | jq -c '.content.data.data')
  echo "$data" | vault kv put -mount=$mount $path -
done
```

### PG in-cluster dump → restore to a fresh postgres
```bash
gpg --decrypt pg-stoa-incluster-2026-05-23.dump.gpg | pg_restore -d stoa -h NEW_HOST -U NEW_USER --no-owner --no-privileges
```

### KC realms → reimport via kcadm or container init
```bash
# Extract tarball, then for each realm:
kcadm create realms -f realm-stoa-config-2026-05-23.json
```

### git-crypt key → unlock repo
```bash
gpg --decrypt git-crypt-stoa-repo-local-2026-05-23.key.gpg > /tmp/gc.key
cd stoa && git-crypt unlock /tmp/gc.key && shred -u /tmp/gc.key
```

### SSH keys → restore to ~/.ssh
```bash
gpg --decrypt ssh-keys-2026-05-23.tar.gz.gpg | tar -xzf - -C /tmp/restored-ssh-keys/
cp /tmp/restored-ssh-keys/ssh-keys/id_ed25519_stoa* ~/.ssh/  # then chmod 600
```

### Git mirrors → re-create remote repo
```bash
gpg --decrypt stoa-strategy-mirror-2026-05-23.tar.gz.gpg | tar -xzf -
cd stoa-strategy.git && git push --mirror git@github.com:NEW_OWNER/stoa-strategy.git
```

## Tokens to REVOKE manually (post-archivage)

Ces creds sont valides au moment du backup. Pour défense en profondeur, révoque côté provider :

| Path Vault | Action |
|---|---|
| `stoa/shared/anthropic.api_key` | Anthropic Console → API Keys → Revoke |
| `stoa/shared/github.token` + `webhook_secret` | GitHub Settings → Developer settings → Personal access tokens → Revoke |
| `stoa/shared/demo-credentials.*` (4 passwords) | Inutiles post-shutdown (KC/OpenSearch/webMethods tués), pas d'action requise |
| `stoa/shared/federation.*` (5 secrets) | Idem (consommateurs dans cluster prod tué) |
| `stoa/shared/stoa-connect.STOA_GATEWAY_API_KEY` | Idem |
| OVH managed PG (`keycloak` + `stoa_production`) | Tués avec l'instance OVH managed Phase 3 |

## NOT backed up (and why)

- **OVH managed PG dumps** (`keycloak` 16MB + `stoa_production` 21MB) : NetworkPolicy + IP whitelist OVH-side block ephemeral pods. KC réutilisable via realms JSON ✓. `stoa_production` = état pre-migration historique, in-cluster `stoa` dump (507MB) couvre la prod live.
- **tooling-vps** : n8n workflows déjà capturés dans HEGEMON w1 backup (`/opt/stoa-ops/n8n-workflows/`). Uptime Kuma/Netbox/PocketBase/Healthchecks = reinstall trivials, valeur unique nulle.
- **HEGEMON workers 2-5** : stateless executors. Toute la config canonique vit sur w1.
- **stoa monorepo public** : déjà sur github.com/stoa-platform/stoa, sera archivé read-only Phase 5.
- **stoa-docs, stoa-web, stoa-quickstart, stoactl** (publics) : idem, sur GitHub, archivés Phase 5.

## Verify procedure (operator, interactive)

Mes subprocess Claude ne peuvent pas invoquer pinentry-mac. Tu dois lancer une fois depuis ton terminal :

```bash
cd ~/Backups/stoa-shutdown && \
  for f in $(find . -name '*.gpg' | sort); do
    echo -n "$f ... "
    if gpg --quiet --decrypt < "$f" > /dev/null 2>&1; then echo OK; else echo FAIL; fi
  done
```

Tape la passphrase une fois au premier prompt → gpg-agent la cache pour les suivants. Attendu : 9× OK.
