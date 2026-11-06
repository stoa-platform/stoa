# stoa-stack

Umbrella chart that installs `stoa-platform` and `stoa-observability` in one
release and derives the parameters they share from a single `global` block.

| Shared parameter | Consumers |
|------------------|-----------|
| `global.environment` | Gateway and sidecar `STOA_ENVIRONMENT`; `environment` label on the gateway, sidecar and control-plane API ServiceMonitors; Alloy `environment` label |
| `global.clusterName` | `cluster` label on the gateway, sidecar and control-plane API ServiceMonitors |
| `global.observability.enabled` | Installs `stoa-observability`; wires gateway/sidecar `STOA_OTEL_ENDPOINT` and NetworkPolicy OTLP egress to its collector. `false` disables all three |
| `global.observability.namespace` | Namespace of the OTLP collector. Empty means co-installed in the release namespace |

When `global` sets a shared parameter, it takes precedence over the
component-local values (`stoaGateway.environment`, `controlPlaneApi.clusterName`,
`stoaSidecar.otelEndpoint`, ...). Standalone installs of `stoa-platform` keep
using those component-local values, so existing deployments are unaffected,
except that the platform overlays' `global.environment` now also reaches the
sidecar and control-plane API labels.

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
