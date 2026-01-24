# ArgoCD Configuration

## OIDC SSO with Keycloak

ArgoCD is configured to use Keycloak for Single Sign-On authentication.

### Components

| File | Description |
|------|-------------|
| `oidc-config.yaml` | ConfigMaps for OIDC and RBAC configuration |

### Authentication Flows

This configuration supports two authentication flows:

1. **Direct SSO Login** - Users login to ArgoCD UI via Keycloak (standard OIDC flow)
2. **API Token Forwarding** - Control-Plane-API forwards user's Keycloak token to ArgoCD API

For flow #2 to work correctly, we must NOT use `enableUserInfoGroups` in the OIDC config.
When ArgoCD receives a forwarded token, it doesn't have the token in its session cache,
so it cannot fetch userinfo. Instead, we rely on JWT claims directly.

### Keycloak Client Configuration

The ArgoCD OIDC client is created in Keycloak with:

- **Client ID**: `argocd`
- **Redirect URI**: `https://argocd.gostoa.dev/auth/callback`
- **Scopes**: openid, profile, email, roles, groups
- **tenant_id Mapper**: Maps Keycloak groups to `tenant_id` claim (used for RBAC)

### OIDC Configuration Details

Key settings in `argocd-cm` ConfigMap:

| Setting | Value | Purpose |
|---------|-------|---------|
| `allowedAudiences` | argocd, control-plane-ui, stoa-portal, etc. | Accept tokens from multiple Keycloak clients |
| `skipAudienceCheckWhenTokenHasNoAudience` | true | Fallback for tokens without explicit audience |
| `codeChallenge` | S256 | PKCE for enhanced security |

**Important**: Do NOT enable `enableUserInfoGroups` - it breaks API token forwarding.

### RBAC Configuration

RBAC uses the `tenant_id` claim from Keycloak tokens (not `groups`).
Users are assigned to Keycloak groups which are included in the `tenant_id` claim.

| Keycloak Group | ArgoCD Role | Permissions |
|----------------|-------------|-------------|
| `argocd-admins` | admin | Full access to all resources |
| `argocd-devops` | devops | Deploy, sync, view applications |
| `argocd-readonly` | readonly | View-only access |
| *(any authenticated user)* | authenticated | Read-only access to applications |

### Deployment

#### Option 1: Ansible Playbook (Recommended)

```bash
# Set Keycloak admin password
export KEYCLOAK_ADMIN_PASSWORD="demo"

# Run playbook
cd ansible
ansible-playbook playbooks/configure-argocd-oidc.yml -e "base_domain=gostoa.dev"
```

#### Option 2: Manual kubectl commands

```bash
# Apply ConfigMaps
kubectl apply -f deploy/argocd/oidc-config.yaml

# Patch secret with client secret (get from Keycloak)
kubectl patch secret argocd-secret -n argocd --type merge -p '{
  "stringData": {
    "oidc.keycloak.clientSecret": "<CLIENT_SECRET>"
  }
}'

# Restart ArgoCD server
kubectl rollout restart deployment argocd-server -n argocd
```

### Testing SSO

1. Go to https://argocd.gostoa.dev
2. Click "Login via Keycloak"
3. Login with your Keycloak credentials
4. Verify role-based access based on group membership

### Testing API Token Forwarding

The Console UI displays ArgoCD application status by forwarding the user's token:

1. Login to Console UI at https://console.gostoa.dev
2. Navigate to Dashboard or Platform Status
3. Verify that ArgoCD application statuses are displayed (Synced, Healthy, etc.)

If you see "Access denied - check ArgoCD RBAC", check:
- The user's `tenant_id` claim contains appropriate groups
- ArgoCD RBAC scopes are set to `[tenant_id, email]`
- `enableUserInfoGroups` is NOT enabled

### Troubleshooting

```bash
# Check ArgoCD logs for auth issues
kubectl logs -n argocd deploy/argocd-server | grep -i -E "(oidc|auth|unauthenticated)"

# Verify OIDC config
kubectl get configmap argocd-cm -n argocd -o jsonpath='{.data.oidc\.config}'

# Verify RBAC config
kubectl get configmap argocd-rbac-cm -n argocd -o yaml

# Check what scopes are configured for RBAC
kubectl get configmap argocd-rbac-cm -n argocd -o jsonpath='{.data.scopes}'

# Decode a JWT token to see claims (replace TOKEN with actual token)
echo "TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq .

# Check Keycloak client
kubectl exec -n stoa-system deploy/keycloak -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields clientId | grep argocd
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Access denied - check ArgoCD RBAC" | Token not accepted | Check `allowedAudiences` includes the client ID |
| "error while querying userinfo endpoint" | `enableUserInfoGroups` is enabled | Remove `enableUserInfoGroups` from OIDC config |
| "cache: key is missing" | ArgoCD trying to use cached token | Disable `enableUserInfoGroups` |
| User has no permissions | Wrong RBAC scope | Ensure `scopes: "[tenant_id, email]"` |

### URLs

- ArgoCD: https://argocd.gostoa.dev
- Console UI: https://console.gostoa.dev
- Keycloak Admin: https://auth.gostoa.dev/admin/stoa/console
- Keycloak OIDC Discovery: https://auth.gostoa.dev/realms/stoa/.well-known/openid-configuration
