# stoa-stack

Umbrella chart that installs `stoa-platform` and `stoa-observability` in one
release and derives the parameters they share from a single `global` block.

| Shared parameter | Consumers |
|------------------|-----------|
| `global.environment` | Gateway and sidecar `STOA_ENVIRONMENT`; `environment` label on the gateway, sidecar and control-plane API ServiceMonitors; Alloy `environment` label |
| `global.clusterName` | `cluster` label on the gateway, sidecar and control-plane API ServiceMonitors |
| `global.observability.enabled` | Installs `stoa-observability`; wires gateway/sidecar `STOA_OTEL_ENDPOINT` and NetworkPolicy OTLP egress to its collector. `false` disables all three |
| `global.observability.namespace` | Namespace of the OTLP collector. Empty means co-installed in the release namespace |

When this umbrella sets `global.observability`, `global.environment` and
`global.clusterName` take precedence over the component-local values
(`stoaGateway.environment`, `controlPlaneApi.clusterName`, ...), and
`global.observability` wires `stoaSidecar.otelEndpoint` / `stoaGateway.otelEndpoint`
to the collector rendered here.

A standalone `stoa-platform` install does not set `global.observability`.
There, a non-empty component environment still overrides `global.environment`,
and an empty component environment inherits it. Platform overlays leave the
component environment empty, so their `global.environment` reaches the
gateway, sidecar and control-plane API labels. Component OTLP endpoints are
unchanged on a standalone install.

## Usage

```bash
helm dependency build charts/stoa-stack
helm lint charts/stoa-stack
helm template stoa charts/stoa-stack --set global.environment=staging
```

Component settings go under the subchart key, for example
`stoa-platform.stoaGateway.replicas`. Do not repeat the shared keys there.

## Coherence tests

```bash
python3 -B -m unittest discover -s charts/stoa-stack/tests -v
```

The tests copy the charts to a temporary directory, build the dependencies
offline, and render them. They check that every consumer follows a change to
a shared parameter and that the OTLP endpoint and NetworkPolicy egress match the
rendered collector Service and pods. They also check that the umbrella's
dependency versions match the sibling charts.
