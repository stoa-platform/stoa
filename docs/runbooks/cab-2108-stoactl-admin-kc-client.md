# Runbook: provision `stoactl-admin` Keycloak client on existing cluster

> **Severity**: Operational — no downtime
> **Last updated**: 2026-04-17
> **Linear Issue**: [CAB-2108](https://linear.app/hlfh-workspace/issue/CAB-2108)

---

## Context

The Helm chart now defines a `stoactl-admin` confidential Keycloak client with the `cpi-admin` realm role assigned to its service-account user, so `stoactl --admin` and CI can obtain admin JWTs via `client_credentials`.

The bootstrap job that creates these clients runs as a `post-install` Helm
hook — `helm.sh/hook: post-install`. Helm **does not re-run it on
`helm upgrade`**, and `create_client` in the script short-circuits on 409.
So on any cluster that was deployed before this change (prod included), the
operator must provision the client manually with the `curl`-based flow
below (or delete the existing job + `helm upgrade` to re-trigger the hook).

## Prerequisites

- Shell access to a pod or workstation with `curl` + `jq`
- Keycloak admin credentials (Infisical: `prod/keycloak/ADMIN_PASSWORD`)
- Infisical write access (to push the generated secret)

**Before you start**, prevent secrets from hitting your shell history:

```bash
# zsh
setopt HIST_IGNORE_SPACE     # lines starting with a space are not saved
# bash (already default with HISTCONTROL)
export HISTCONTROL=ignorespace:erasedups
# Prefix every command in this runbook with a leading space.
```

Exports below use `read -s` for the admin password so it's never on the
command line:

```bash
export KC=https://auth.gostoa.dev
export REALM=stoa
export ADMIN_USER=admin
# Fetch via infisical (uses cached session creds, not on argv):
ADMIN_PASS=$(infisical secrets get ADMIN_PASSWORD --env prod --path /keycloak --plain)
```

## Steps

### 1. Get a master-realm admin token

```bash
TOKEN=$(curl -sf -X POST "$KC/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli \
  -d "username=$ADMIN_USER" -d "password=$ADMIN_PASS" | jq -r .access_token)
```

### 2. Create the client (idempotent — 409 if exists)

```bash
curl -sf -X POST "$KC/admin/realms/$REALM/clients" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "clientId": "stoactl-admin",
    "name": "STOA CLI Admin (service account)",
    "enabled": true,
    "publicClient": false,
    "serviceAccountsEnabled": true,
    "standardFlowEnabled": false,
    "directAccessGrantsEnabled": false
  }'
```

### 3. Assign `cpi-admin` to the service-account user

```bash
CLIENT_UUID=$(curl -sf -H "Authorization: Bearer $TOKEN" \
  "$KC/admin/realms/$REALM/clients?clientId=stoactl-admin" | jq -r '.[0].id')

SA_USER_ID=$(curl -sf -H "Authorization: Bearer $TOKEN" \
  "$KC/admin/realms/$REALM/clients/$CLIENT_UUID/service-account-user" | jq -r .id)

ROLE=$(curl -sf -H "Authorization: Bearer $TOKEN" \
  "$KC/admin/realms/$REALM/roles/cpi-admin")

curl -sf -X POST "$KC/admin/realms/$REALM/users/$SA_USER_ID/role-mappings/realm" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "[$ROLE]"
```

### 4. Retrieve the generated client secret

```bash
# Capture into a variable without echoing. Do not run `set -x` in this shell.
SECRET=$(curl -sf -H "Authorization: Bearer $TOKEN" \
  "$KC/admin/realms/$REALM/clients/$CLIENT_UUID/client-secret" | jq -r .value)
[ -n "$SECRET" ] || { echo "ERR: failed to retrieve secret" >&2; exit 1; }
```

### 5. Push secret to Infisical

```bash
infisical secrets set STOACTL_ADMIN_CLIENT_SECRET="$SECRET" \
  --env prod --path /gateway --type shared
unset SECRET   # clear from shell history / environment
```

## Verification

The steps below pass the secret via stdin (`--data-binary @-`) rather than as
a `-d` flag value, so it never appears in the process listing or shell
history. The generated JWT is short-lived (5 min) and is decoded into a
variable instead of being printed directly:

```bash
# a) Obtain an admin token via client_credentials (secret via stdin)
JWT=$(printf 'grant_type=client_credentials&client_id=stoactl-admin&client_secret=%s' "$SECRET" \
  | curl -sf -X POST "$KC/realms/$REALM/protocol/openid-connect/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      --data-binary @- | jq -r .access_token)

# b) Confirm cpi-admin is in the token without logging the JWT itself
ROLES=$(printf '%s' "$JWT" | cut -d. -f2 | base64 -d 2>/dev/null | jq -r '.realm_access.roles | join(",")')
echo "roles: $ROLES"   # → expect a comma-separated list containing cpi-admin

# c) Admin endpoint should return 200, not 403
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $JWT" \
  https://api.gostoa.dev/v1/admin/mcp/servers
# → 200

# d) stoactl end-to-end (read-only check)
STOA_ADMIN_KEY="$JWT" stoactl get apis --admin
unset JWT
```

## Secret handling + rotation

- **Never** pass the secret via `-d "key=$SECRET"` on the command line: on
  shared hosts it appears in `ps auxe` for the lifetime of the curl process.
  Use stdin with `--data-binary @-` or a file with `--data-urlencode @file`
  and delete the file afterward.
- **Never** log the secret (no `echo "$SECRET"`, no `set -x`).
- **Rotation policy**: rotate the secret every 90 days, and immediately on
  suspected compromise or whenever a team member with access leaves.
  Rotation procedure:
  ```bash
  # Regenerate in Keycloak (invalidates the old value)
  NEW=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
    "$KC/admin/realms/$REALM/clients/$CLIENT_UUID/client-secret" | jq -r .value)
  # Update Infisical (consumers pick up on next read — no restart)
  infisical secrets set STOACTL_ADMIN_CLIENT_SECRET="$NEW" \
    --env prod --path /gateway --type shared
  unset NEW
  ```

## Rollback

If the new client misbehaves, delete it (SA and role-mapping are cascaded):

```bash
curl -sf -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$KC/admin/realms/$REALM/clients/$CLIENT_UUID"
```

Consumers of `STOACTL_ADMIN_CLIENT_SECRET` will start getting 401 — coordinate before deleting.
