# Installation

The `stoa-platform` Helm chart currently installs the **Rust STOA Gateway** and
supporting resources. The Control Plane API, console, Developer Portal, Keycloak,
PostgreSQL and observability servers are **not yet provided by the chart**.

Use the [gateway installation guide](../installation.md) for the template
inventory, prerequisites, placeholder values and installation commands. Run its
commands from the repository root.

## Administrator Checklist

1. Supply your own Control Plane API, Keycloak and credentials when using their
   integrations. Their URLs in values configure connections to existing services.
2. Prepare `my-values.yaml` from the [configuration example](../installation.md#configure-values).
   The example disables OpenAPI sync and ServiceMonitor resources that otherwise
   require services or operators outside the release.
3. Follow [Install with Helm](../installation.md#install-with-helm). Helm installs
   missing CRDs on initial installation; existing CRDs need separate review on upgrade.
4. Follow [Verify the Gateway](../installation.md#verify-the-gateway). Check the
   `stoa-gateway` Deployment and Service, then `/health` and `/ready` via port-forward.

## Expected Result

| Resource | Expected with the guide's values |
|----------|----------------------------------|
| `stoa-gateway` Deployment | Rust gateway pods |
| `stoa-gateway` Service | ClusterIP, port **80** to container port **8080** |
| Policy ConfigMap, internal Secret and API configuration ConfigMaps | Supporting configuration; no API workload |
| Tool, ToolSet, Skill, GatewayInstance and GatewayBinding CRDs | Resource definitions; no tenant or tool instances created |

Ingress, ServiceMonitor resources and OpenAPI sync Jobs are disabled by the
example. HPA/PDB, sidecar and bootstrap resources remain opt-in. They do not
install the external services they reference.

## Separately Managed Services

Database migrations, Keycloak realm setup and initial tenant creation belong to
separately deployed control-plane services. These are not post-install steps for
a gateway-only release. Console, portal and API health checks require those
services to exist first.

The chart's current `helm test` includes API and Keycloak checks; use the gateway
checks linked above for this release. Helm notes list platform URLs even when
those services are absent.
