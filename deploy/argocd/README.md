# ArgoCD Configuration

## OIDC SSO with Keycloak (Native, no Dex)

ArgoCD uses **native OIDC** (not Dex) for Keycloak SSO. This was migrated from
Dex in March 2026 to simplify the stack (single IdP, no broker needed).

### Prerequisites

| Component | Requirement |
|-----------|-------------|
| Keycloak client | `argocd` with redirect URI `https://argocd.gostoa.dev/auth/callback` |
| Protocol mapper | `realm-roles` → `groups` claim on `argocd` client |
| CoreDNS | `coredns-custom` rewrite: `auth.gostoa.dev` → `ingress-nginx-controller.ingress-nginx.svc` |
| NetworkPolicy | `allow-argocd-to-keycloak` in `k8s/network-policies/20-argocd.yaml` |
| Secret | `oidc.keycloak.clientSecret` in `argocd-secret` |

### Hairpin NAT Workaround

`auth.gostoa.dev` resolves to the nginx-gateway-fabric LoadBalancer external IP (`92.222.226.6`).
OVH MKS does not support hairpin NAT — pods cannot reach their own cluster's external LB IP.

**Solution**: CoreDNS rewrite in `coredns-custom` (kube-system) redirects `auth.gostoa.dev`
to the `ingress-nginx-controller` ClusterIP, which terminates TLS and forwards to Keycloak.

```yaml
# coredns-custom ConfigMap (kube-system)
data:
  auth-hairpin.include: |
    rewrite name auth.gostoa.dev ingress-nginx-controller.ingress-nginx.svc.cluster.local
```

A NetworkPolicy (`allow-argocd-to-keycloak`) permits egress from argocd pods to ingress-nginx.

### Authentication Flows

1. **Direct SSO Login** — Users click "Login via Keycloak" on ArgoCD UI
2. **API Token Forwarding** — Control-Plane-API forwards user's Keycloak token to ArgoCD API

For flow #2: do NOT use `enableUserInfoGroups` (breaks forwarded token lookup).

### RBAC

Realm roles from Keycloak are mapped to ArgoCD roles via the `groups` JWT claim.

| Keycloak Realm Role | ArgoCD Role | Permissions |
|---------------------|-------------|-------------|
| `cpi-admin` | cpi-admin | Full access to all resources |
| `devops` | devops | Deploy, sync, view applications |
| `viewer` | readonly | View-only access |

### Deployment

```bash
# 1. Apply ConfigMaps
kubectl apply -f deploy/argocd/oidc-config.yaml

# 2. Patch secret with client secret (get from Keycloak admin console)
kubectl patch secret argocd-secret -n argocd --type merge -p '{
  "stringData": {
    "oidc.keycloak.clientSecret": "<CLIENT_SECRET>"
  }
}'

# 3. Restart ArgoCD server
kubectl rollout restart deployment argocd-server -n argocd
```

### Troubleshooting

```bash
# Check OIDC config
kubectl get configmap argocd-cm -n argocd -o jsonpath='{.data.oidc\.config}'

# Check auth logs
kubectl logs -n argocd deploy/argocd-server | grep -i -E "(oidc|auth|error)"

# Test Keycloak connectivity from inside cluster
kubectl run -n argocd curl-test --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sk https://auth.gostoa.dev/realms/stoa/.well-known/openid-configuration

# Verify CoreDNS rewrite
kubectl run -n argocd dns-test --rm -it --restart=Never --image=curlimages/curl -- \
  nslookup auth.gostoa.dev
```

| Issue | Cause | Solution |
|-------|-------|----------|
| `dial tcp 92.222.226.6:443: i/o timeout` | Hairpin NAT — pods can't reach own LB | Add CoreDNS rewrite (see above) |
| `key does not exist in secret` (warning) | ArgoCD v3.x init race | Benign — secret resolves after startup |
| 403 after login | Wrong RBAC scope or missing role | Check `scopes: '[groups]'` in argocd-rbac-cm |
| No "Login via Keycloak" button | `oidc.config` not set | Verify argocd-cm has `oidc.config` key |
