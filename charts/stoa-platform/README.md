# Helm Chart — stoa-platform

Helm 3 chart for deploying STOA Platform to Kubernetes.

## Prerequisites

- Kubernetes 1.28+
- Helm 3.12+
- Container images pushed to [the STOA container registry](https://github.com/orgs/stoa-platform/packages)

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

### Global

| Key | Default | Description |
|-----|---------|-------------|
| `stoa.domain` | `gostoa.dev` | Base domain for all service URLs |
| `stoa.adminEmail` | `""` | Admin email for initial setup |
| `stoa.anthropicApiKey` | `""` | Anthropic key (empty = chat disabled) |
| `stoa.bootstrap.enabled` | `false` | Run post-install bootstrap Job |
| `stoa.bootstrap.keycloak.adminUser` | `admin` | Keycloak admin username |
| `stoa.bootstrap.keycloak.adminPassword` | `""` | Keycloak admin password |
| `stoa.bootstrap.defaultTenant.name` | `default` | Default tenant slug |

### Gateway

| Key | Default | Description |
|-----|---------|-------------|
| `stoaGateway.enabled` | `true` | Deploy the Rust gateway |
| `stoaGateway.replicas` | `2` | Pod replica count |
| `stoaGateway.image.repository` | [STOA Gateway](https://github.com/stoa-platform/stoa/pkgs/container/stoa-gateway) | Container image |
| `stoaGateway.image.digest` | See `values.yaml` | Immutable image digest |
| `stoaGateway.controlPlaneUrl` | `http://stoa-control-plane-api.stoa-system.svc.cluster.local:8000` | Control Plane API URL (in-cluster Service, port 8000) |
| `stoaGateway.policyBootTenants` | `[]` | Tenants whose tool policy is loaded at startup. Rendered as comma-separated `STOA_POLICY_BOOT_TENANTS` when non-empty; `/ready` fails closed until their policy has loaded (ADR-070) |
| `stoaGateway.keycloakUrl` | `http://keycloak:8080` | OIDC provider |
| `stoaGateway.mode` | `edge-mcp` | Gateway mode (edge-mcp, sidecar, proxy, shadow) |
| `stoaGateway.autoRegister` | `true` | Register with control plane on startup |
| `stoaGateway.ingress.enabled` | `true` | Create Ingress resource |
| `stoaGateway.ingress.host` | `mcp.<YOUR_DOMAIN>` | Ingress hostname |
| `stoaGateway.serviceMonitor.enabled` | `true` | Create Prometheus ServiceMonitor |
| `stoaGateway.resources.requests.memory` | `128Mi` | Memory request |
| `stoaGateway.resources.limits.memory` | `256Mi` | Memory limit |
| `stoaSidecar.enabled` | `false` | Deploy a real same-pod third-party gateway + STOA sidecar |
| `stoaSidecar.controlPlaneUrl` | `http://stoa-control-plane-api.stoa-system.svc.cluster.local:8000` | Control Plane API URL for the sidecar container |
| `stoaSidecar.policyBootTenants` | `[]` | Same semantics as `stoaGateway.policyBootTenants`, for the sidecar container |
| `gatewaySync.enabled` | `false` | Enable OpenAPI sync CronJob |
| `gatewaySync.schedule` | `*/30 * * * *` | Sync frequency |
| `autoscaling.enabled` | `false` | Enable HPA |
| `podDisruptionBudget.enabled` | `false` | Enable PDB |

### Gateway routing, federation and API proxy

These settings use the existing gateway runtime contracts and defaults:

| Value under `stoaGateway` | Default | Environment variable |
|---|---|---|
| `routing.reloadEnabled` / `reloadIntervalSecs` | `false` / `30` | `STOA_ROUTE_RELOAD_ENABLED` / `STOA_ROUTE_RELOAD_INTERVAL_SECS` |
| `federation.enabled` | `false` | `STOA_FEDERATION_ENABLED` |
| `federation.cacheTtlSecs` / `cacheMaxEntries` | `300` / `10000` | `STOA_FEDERATION_CACHE_TTL_SECS` / `STOA_FEDERATION_CACHE_MAX_ENTRIES` |
| `apiProxy.enabled` / `requireAuth` | `false` / `true` | `STOA_API_PROXY__ENABLED` / `STOA_API_PROXY__REQUIRE_AUTH` |

Route reload refreshes routes from `controlPlaneUrl`. Federation requires
`federation.upstreamsSecretRef: {name: existing-secret, key: upstreams}` pointing
to an existing Secret containing the non-empty JSON upstream array consumed by
`STOA_FEDERATION_UPSTREAMS`. Upstream entries accept `url`, `transport`,
`timeout_secs`, and optional `auth_token`. Tokens must only come from that Secret;
never put token values in Helm values. This chart does not create the Secret.

`apiProxy.backends` maps lowercase backend identifiers to gateway snake_case
fields, rendered as `STOA_API_PROXY__BACKENDS__<NAME>__<FIELD>`:

```yaml
stoaGateway:
  apiProxy:
    enabled: true
    backends:
      catalog:
        enabled: true
        base_url: https://catalog.example.test
        auth_type: none
        required_scopes: [catalog:read]
        allowed_paths: [/items]
```

Other supported fields are `auth_header`, `rate_limit_rpm`, `timeout_secs`,
`circuit_breaker_enabled`, `fallback_direct`, `required_roles`, and `public`.
Omitted backend fields retain runtime defaults (disabled, bearer authentication,
30-second timeout, circuit breaker enabled, no direct fallback). Keep
`requireAuth: true` outside development. Non-public backends need scopes or roles;
public backends require `auth_type: none` and no scopes or roles. Backend service
credentials remain in the existing gateway credential store, never in values.
When NetworkPolicy is enabled, explicitly allow the intended upstream egress.

Run offline render tests with
`python3 -B -m unittest discover -s charts/stoa-platform/tests -v`.

### Environment overrides

| File | Environment | Usage |
|------|-------------|-------|
| `values-dev.yaml` | Local / CI | `helm upgrade ... -f values-dev.yaml` |
| `values-staging.yaml` | Staging (local/CI) | Manual apply |
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
| `secret-internal.yaml` | Auto-generated shared keys |
| `bootstrap-job.yaml` | Post-install bootstrap Job |
| `control-plane-api-chat-config.yaml` | Chat kill-switch ConfigMap |
| `tests/test-connection.yaml` | Helm test Pod |

### STOA Sidecar

`stoaSidecar.enabled=true` renders one `Deployment` containing both the target
gateway container (`stoaSidecar.mainGateway`) and the `stoa-sidecar` container.
The target gateway must call `http://localhost:8081/authz`; the sidecar binds
`127.0.0.1:8081` inside the pod and exposes only the main gateway Service.

The chart fails rendering if `stoaSidecar.enabled=true` and
`stoaSidecar.mainGateway.enabled=false`, because that would be a standalone
authz service rather than a Kubernetes sidecar. Standalone remote links are kept
under `k8s/gateways/base/stoa-link-wm` and are labelled
`stoa.io/deployment-kind=standalone-link`.

For a wired Nginx/OpenResty example, render with:

```sh
helm template companion charts/stoa-platform -f charts/stoa-platform/examples/companion-nginx.yaml
python3 -m unittest discover -s scripts/tests -p test_companion_helm.py
```

`stoaSidecar.nginxExample` is off by default. Set `authSecret` to an existing
Secret containing an `htpasswd` key, `tenantId` to the tenant assigned to those
users, and `backendUrl` to an HTTP backend origin. Use a TLS ingress for Basic
authentication; the example Service is ClusterIP. Nginx authenticates first,
then sends the authenticated username and configured tenant to the existing
`POST /authz` decision endpoint. Client-supplied identity headers are not trusted.
Only a 200 decision permits proxying; denial, timeout and connection failure
stop the request. This example grants no roles or scopes. The ConfigMap and
read-only Secret mount are rendered only when the example is enabled.
See [sidecar usage and limits](../../docs/integrations/sidecar-usage-patterns.md)
for the existing decision contract and runtime limitations.

Image references use immutable registry digests. Set both `repository` and
`digest` when overriding gateway or companion images; tag-only overrides do not
change the selected image. The retired Python gateway image and the
registry-restricted webMethods image have no default reference. Supply your own
immutable image before enabling a webMethods companion. The OpenResty example
includes its own pin. Companion and Nginx example defaults remain disabled.

### Rollback-safe image policy

Gateway and companion images render as `repository@sha256:...` and default to
`image.pullPolicy: IfNotPresent`. Set the digest for each release and retain
previous digests in the registry so Helm can restore the exact previous image.
`IfNotPresent` alone cannot make a mutable tag such as `latest` reproducible.
Control-plane deployments are managed by standalone manifests, outside this chart.

Sync Jobs, the bootstrap Job and the Helm connection-test Pod also default to
`IfNotPresent`. Override `gatewaySync.pullPolicy`, `stoa.bootstrap.pullPolicy`
or `testConnection.pullPolicy` when needed. Deployment pull policies remain
configurable under each component's `image.pullPolicy`.

## CRDs

Custom Resource Definitions in `crds/` (applied separately, not managed by Helm lifecycle):

| CRD | API Group | Description |
|-----|-----------|-------------|
| `tools.gostoa.dev` | gostoa.dev/v1alpha1 | MCP Tool definitions |
| `toolsets.gostoa.dev` | gostoa.dev/v1alpha1 | Tool groupings |
| `gatewayinstances.gostoa.dev` | gostoa.dev/v1alpha1 | Gateway instance registration |
| `skills.gostoa.dev` | gostoa.dev/v1alpha1 | MCP Skill definitions |
| `gatewaybindings.gostoa.dev` | gostoa.dev/v1alpha1 | Gateway-to-tool bindings |

## Architecture

```
ArgoCD watches charts/stoa-platform/ on main
  └── Renders templates with values-{env}.yaml
      ├── stoa-gateway Deployment (Rust, 2 replicas)
      ├── Service + Ingress (mcp.example.com)
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
- **Depended on by**: ArgoCD (GitOps deployment to OVH)
