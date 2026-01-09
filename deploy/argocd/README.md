# ArgoCD Configuration

## OIDC SSO with Keycloak

ArgoCD is configured to use Keycloak for Single Sign-On authentication.

### Components

| File | Description |
|------|-------------|
| `oidc-config.yaml` | ConfigMaps for OIDC and RBAC configuration |

### Keycloak Client Configuration

The ArgoCD OIDC client is created in Keycloak with:

- **Client ID**: `argocd`
- **Redirect URI**: `https://argocd.stoa.cab-i.com/auth/callback`
- **Scopes**: openid, profile, email, roles
- **Groups Mapper**: Maps Keycloak groups to `groups` claim

### RBAC Groups

| Keycloak Group | ArgoCD Role | Permissions |
|----------------|-------------|-------------|
| `argocd-admins` | admin | Full access to all resources |
| `argocd-devops` | devops | Deploy, sync, view applications |
| `argocd-readonly` | readonly | View-only access |

### Deployment

#### Option 1: Ansible Playbook (Recommended)

```bash
# Set Keycloak admin password
export KEYCLOAK_ADMIN_PASSWORD="demo"

# Run playbook
cd ansible
ansible-playbook playbooks/configure-argocd-oidc.yml -e "base_domain=stoa.cab-i.com"
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

1. Go to https://argocd.stoa.cab-i.com
2. Click "Login via Keycloak"
3. Login with your Keycloak credentials
4. Verify role-based access based on group membership

### Troubleshooting

```bash
# Check ArgoCD logs
kubectl logs -n argocd deploy/argocd-server | grep -i oidc

# Verify OIDC config
kubectl get configmap argocd-cm -n argocd -o jsonpath='{.data.oidc\.config}'

# Check Keycloak client
kubectl exec -n stoa-system deploy/keycloak -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields clientId | grep argocd
```

### URLs

- ArgoCD: https://argocd.stoa.cab-i.com
- Keycloak Admin: https://auth.stoa.cab-i.com/admin/stoa/console
- Keycloak OIDC Discovery: https://auth.stoa.cab-i.com/realms/stoa/.well-known/openid-configuration
