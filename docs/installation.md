# STOA Gateway Installation Guide

The `charts/stoa-platform` Helm chart currently deploys the **Rust STOA Gateway**
and supporting Kubernetes resources. It does not install the full STOA Platform.
Run the commands below from the repository root after replacing all placeholders.

## What the Chart Installs

The inventory below follows the [templates](../charts/stoa-platform/templates/)
and [default values](../charts/stoa-platform/values.yaml):

| Resource | Current behavior |
|----------|------------------|
| Gateway Deployment and ClusterIP Service | Enabled by default; two replicas, Service port **80** to container port **8080** |
| Gateway policy ConfigMap | Enabled by default and mounted in the gateway |
| Internal Secret and API configuration ConfigMaps | Created by the chart; configuration alone does not deploy the API |
| ServiceMonitor objects | Enabled by default for the Rust gateway, legacy MCP gateway and Control Plane API; require an existing Prometheus Operator |
| OpenAPI sync CronJob and post-install/upgrade Job | Enabled by default; require an existing Control Plane API, webMethods gateway and credentials |
| Five CRDs in `crds/` | Tool, ToolSet, Skill, GatewayInstance and GatewayBinding definitions; Helm installs missing CRDs on initial installation |
| Optional resources | Ingress, watcher RBAC, ExternalSecret, HPA/PDB, sidecar, bootstrap Jobs and other integration resources depend on their values |

### Not Yet Provided by the Chart

| Component or task | Installation responsibility |
|-------------------|-----------------------------|
| Control Plane API, console and Developer Portal | Not yet provided by the chart; deploy separately |
| Keycloak and PostgreSQL | Not yet provided by the chart; supply separately for control-plane workflows |
| Kafka/Redpanda, Vault and object storage | Not yet provided by the chart; provision separately when needed |
| Prometheus/Grafana and their operators | Not yet provided by the chart; ServiceMonitor objects only describe scrape targets |
| Ingress controller, certificates and External Secrets Operator | Not yet provided by the chart; supply before enabling the corresponding integrations |
| Database migrations, realm configuration and tenant creation | Require separately deployed services; a gateway release does not complete these workflows |

The chart has no dependency charts that install these services. Values for API
monitoring, console autoscaling or bootstrap hooks do not create their workloads.

## Prerequisites

- An existing Kubernetes cluster (1.28+) with `kubectl` configured
- Helm 3.12+ and access to the selected gateway container image
- For an integrated gateway: reachable Control Plane API and Keycloak endpoints,
  plus an existing gateway credential Secret managed by your operator

## Configure Values

Create `my-values.yaml` using the following example. Replace every
`REPLACE_WITH_...` value and URL placeholder with your own configuration. Keep
credential values in your secret manager; only reference an existing Secret here.

```yaml
stoa:
  domain: REPLACE_WITH_YOUR_BASE_DOMAIN

stoaGateway:
  enabled: true
  image:
    # Pin the gateway image by digest at install time:
    # --set stoaGateway.image.tag=<release> --set stoaGateway.image.digest=sha256:<64-hex digest>
  controlPlaneUrl: "https://<YOUR_CONTROL_PLANE_HOST>"
  keycloakUrl: "https://<YOUR_KEYCLOAK_HOST>"
  secretName: REPLACE_WITH_EXISTING_GATEWAY_SECRET_NAME
  ingress:
    enabled: false
  serviceMonitor:
    enabled: false
  otelEndpoint: ""

gateway:
  edgeMcp:
    enabled: false

gatewaySync:
  enabled: false

controlPlaneApi:
  serviceMonitor:
    enabled: false
```

This example disables the OpenAPI sync Jobs and the monitors for services absent
from the release. It also disables the gateway ServiceMonitor so an existing
Prometheus Operator is optional, and disables export to an external OTLP collector.
`gateway.edgeMcp.enabled` controls the legacy ServiceMonitor; disabling it does
not disable the Rust gateway, which uses `stoaGateway.enabled`.

Enable integrations only after their external prerequisites are available. Setting
`stoaGateway.ingress.enabled` requires your own hostname, ingress controller and
TLS configuration. The example exposes the gateway through its ClusterIP Service.

## Install with Helm

```bash
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system --create-namespace \
  -f my-values.yaml
```

Helm installs missing CRDs from `crds/` on the first install; a separate
`kubectl apply` is not required for that step. Helm does not upgrade existing CRDs
on subsequent upgrades; review CRD changes separately before updating them.

## Verify the Gateway

```bash
kubectl rollout status deployment/stoa-gateway -n stoa-system
kubectl get pods -n stoa-system -l app.kubernetes.io/name=stoa-gateway
kubectl get service stoa-gateway -n stoa-system
kubectl port-forward -n stoa-system service/stoa-gateway 8080:80
```

With the port-forward running, use another terminal:

```bash
curl --fail http://localhost:8080/health
curl --fail http://localhost:8080/ready
```

The expected application Service is `stoa-gateway` on port **80**. API, console,
portal and Keycloak endpoints are only available if installed separately.
The chart's current Helm test also checks API and Keycloak, so it is not a
standalone gateway check. The URLs printed by Helm notes do not confirm that
those services were deployed.

## Upgrade and Troubleshooting

Reuse your reviewed values file for upgrades:

```bash
helm upgrade stoa-platform ./charts/stoa-platform \
  -n stoa-system -f my-values.yaml
```

If the gateway is not ready, inspect its pod events and logs, selected image,
resource capacity and connectivity to the configured external services.
See the [admin installation checklist](./admin/installation.md) and
[runbook index](./runbooks/README.md) for operational context.
