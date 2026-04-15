# Helm Chart — stoa-platform

## Overview
Helm 3 chart for deploying the STOA Platform to Kubernetes. Manages gateway deployments, secrets, service monitors, and OpenAPI sync jobs.

## Chart Info
- Name: `stoa-platform`
- Version: 0.1.0
- AppVersion: 2.0.0

## Templates
| Template | Purpose |
|----------|---------|
| `_helpers.tpl` | Template helpers |
| `stoa-gateway-deployment.yaml` | Rust gateway Deployment |
| `stoa-gateway-secret.yaml` | Gateway secrets (JWT_SECRET, etc.) |
| `stoa-gateway-service.yaml` | Gateway Service |
| `stoa-gateway-servicemonitor.yaml` | Prometheus ServiceMonitor |
| `gateway-openapi-sync-job.yaml` | CronJob for OpenAPI sync |

## Values Structure
```yaml
gateway:              # Python mcp-gateway (current production)
  image: ...
  edgeMcp: ...        # Edge-MCP mode config
  sidecar: ...        # Future
  proxy: ...          # Future
  shadow: ...         # Future

stoaGateway:          # Rust gateway (emerging, disabled by default)
  enabled: false
  image: ...
  replicas: 1
  controlPlaneUrl: ...
  keycloakUrl: ...
  resources: ...

gatewaySync:          # OpenAPI sync to webMethods
  enabled: false
  schedule: "*/30 * * * *"
```

## Values Overrides
| File | Environment |
|------|-------------|
| `values.yaml` | Base/default |
| `values-dev.yaml` | Dev |
| `values-staging.yaml` | Staging |
| `values-prod.yaml` | Production |

## Commands
```bash
helm lint charts/stoa-platform
helm template stoa-platform ./charts/stoa-platform  # Dry-run
helm upgrade --install stoa-platform ./charts/stoa-platform -n stoa-system --create-namespace
```

## Release Workflow
- **Workflow**: `.github/workflows/helm-release.yml`
- **Trigger**: Push to main changing `charts/stoa-platform/Chart.yaml`
- **Creates**: Git tag `helm-vX.Y.Z` + GitHub Release with packaged `.tgz`
- **Idempotent**: Skips if tag already exists

## Dependencies
- **Depends on**: Container images (control-plane-api, mcp-gateway, stoa-gateway)
- **Depended on by**: ArgoCD (GitOps deployment)

## Règles

Détail on-demand: `.claude/docs/k8s-deploy.md`, `secrets-management.md`.

- `securityContext.privileged: false` EXPLICITE sur chaque container (Kyverno Enforce bloque sinon).
- `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`.
- `strategy.rollingUpdate.maxUnavailable: 1, maxSurge: 0` sur deployments single-replica (sinon deadlock).
- Nginx container: `readOnlyRootFilesystem: false` (envsubst écrit dans `/etc/nginx/conf.d/`).
- `proxy_pass` nginx: TOUJOURS via variable (`set $be "$VAR"; proxy_pass $be;`). Jamais hostname statique (crash au startup).
- envsubst: custom script dans `/docker-entrypoint.d/19-*.sh` + template dans `/etc/nginx/custom-templates/`. JAMAIS `NGINX_ENVSUBST_FILTER`.
- Probes sur `/health` dédié, jamais `/`.
- Port services: doit matcher `charts/*/values.yaml` côté stoa-infra. Mismatch = connexion silencieusement cassée.
- CI: `apply-manifest` obligatoire entre `docker` et `deploy`. Jamais `kubectl replace --force` ni `--server-side`.
- Secrets K8s: `REPLACE_FROM_VAULT` placeholder. Jamais valeur réelle (gitleaks + pre-edit hook bloquent).
