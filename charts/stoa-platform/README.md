# Helm Chart — stoa-platform

Helm 3 chart for deploying STOA Platform to Kubernetes.

## Prerequisites

- Kubernetes 1.28+
- Helm 3.12+
- Container images pushed to `ghcr.io/stoa-platform/`

## Quick Start

```bash
# Lint
helm lint charts/stoa-platform

# Dry-run (render templates without installing)
helm template stoa-platform ./charts/stoa-platform -n stoa-system

# Install / upgrade
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system --create-namespace

# Apply CRDs (not managed by Helm)
kubectl apply -f charts/stoa-platform/crds/
```

## Key Values

| Key | Default | Description |
|-----|---------|-------------|
| `stoaGateway.enabled` | `true` | Deploy the Rust gateway |
| `stoaGateway.replicas` | `2` | Pod replica count |
| `stoaGateway.image.repository` | `ghcr.io/stoa-platform/stoa-gateway` | Container image |
| `stoaGateway.image.tag` | `latest` | Image tag |
| `stoaGateway.controlPlaneUrl` | `http://control-plane-api:8000` | API sync endpoint |
| `stoaGateway.keycloakUrl` | `http://keycloak:8080` | OIDC provider |
| `stoaGateway.mode` | `edge-mcp` | Gateway mode (edge-mcp, sidecar, proxy, shadow) |
| `stoaGateway.autoRegister` | `true` | Register with control plane on startup |
| `stoaGateway.ingress.enabled` | `true` | Create Ingress resource |
| `stoaGateway.ingress.host` | `mcp.<YOUR_DOMAIN>` | Ingress hostname |
| `stoaGateway.serviceMonitor.enabled` | `true` | Create Prometheus ServiceMonitor |
| `stoaGateway.resources.requests.memory` | `128Mi` | Memory request |
| `stoaGateway.resources.limits.memory` | `256Mi` | Memory limit |
| `stoaSidecar.enabled` | `false` | Deploy sidecar mode (future) |
| `gatewaySync.enabled` | `false` | Enable OpenAPI sync CronJob |
| `gatewaySync.schedule` | `*/30 * * * *` | Sync frequency |
| `autoscaling.enabled` | `false` | Enable HPA |
| `podDisruptionBudget.enabled` | `false` | Enable PDB |

### Environment overrides

| File | Environment | Usage |
|------|-------------|-------|
| `values-dev.yaml` | Local / CI | `helm upgrade ... -f values-dev.yaml` |
| `values-staging.yaml` | Hetzner K3s | ArgoCD auto-sync |
| `values-prod.yaml` | OVH MKS | ArgoCD auto-sync |

## Templates

| Template | Resource |
|----------|----------|
| `stoa-gateway-deployment.yaml` | Gateway Deployment |
| `stoa-gateway-service.yaml` | Gateway Service |
| `stoa-gateway-ingress.yaml` | Gateway Ingress |
| `stoa-gateway-secret.yaml` | Gateway secrets |
| `stoa-gateway-servicemonitor.yaml` | Prometheus ServiceMonitor |
| `stoa-gateway-rbac.yaml` | RBAC (ServiceAccount, Role, RoleBinding) |
| `stoa-gateway-policy-configmap.yaml` | OPA policy ConfigMap |
| `stoa-sidecar-deployment.yaml` | Sidecar mode Deployment |
| `gateway-openapi-sync-job.yaml` | OpenAPI sync CronJob |

## CRDs

Custom Resource Definitions in `crds/` (applied separately, not managed by Helm lifecycle):

| CRD | API Group | Description |
|-----|-----------|-------------|
| `tools.gostoa.dev` | `gostoa.dev/v1alpha1` | MCP Tool definitions |
| `toolsets.gostoa.dev` | `gostoa.dev/v1alpha1` | Tool groupings |
| `gatewayinstances.gostoa.dev` | `gostoa.dev/v1alpha1` | Gateway instance registration |
| `skills.gostoa.dev` | `gostoa.dev/v1alpha1` | MCP Skill definitions |
| `gatewaybindings.gostoa.dev` | `gostoa.dev/v1alpha1` | Gateway-to-tool bindings |

## Architecture

```
ArgoCD watches charts/stoa-platform/ on main
  └── Renders templates with values-{env}.yaml
      ├── stoa-gateway Deployment (Rust, 2 replicas)
      ├── Service + Ingress (mcp.gostoa.dev)
      ├── ServiceMonitor (Prometheus scrape)
      └── CRDs (applied separately)
```

## Testing

```bash
# Lint chart
helm lint charts/stoa-platform

# Render and review output
helm template stoa-platform ./charts/stoa-platform -f charts/stoa-platform/values-staging.yaml

# Diff against live (requires helm-diff plugin)
helm diff upgrade stoa-platform ./charts/stoa-platform -n stoa-system
```

## Dependencies

- **Depends on**: Container images (stoa-gateway, mcp-gateway)
- **Depended on by**: ArgoCD (GitOps deployment to OVH + Hetzner)
