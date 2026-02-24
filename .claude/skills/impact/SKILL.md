# /impact — Service Impact Analysis

## Trigger

User runs `/impact <service>` to answer: "If I kill this service, what breaks?"

## Steps

### 1. Validate Service

```bash
./scripts/ops/catalog-graph.sh --reverse <service>
```

If service not found, show the error (lists available services).

### 2. Show Reverse Dependencies

Display the table output from `--reverse` — shows all impacted services with depth (direct vs transitive) and type.

### 3. Show Impact Graph

```bash
./scripts/ops/catalog-graph.sh --impact <service>
```

Display the Mermaid subgraph (colored: red=down, orange=direct, yellow=transitive).

### 4. Enrich with Live State (optional)

If `kubectl` is available and configured, enrich with pod status:

```bash
# For each impacted service, check live state
kubectl get pods -n stoa-system -l app=<service-name> -o wide --no-headers 2>/dev/null
```

Present enriched table:

| Service | Impact | Pods | Status | Image |
|---------|--------|------|--------|-------|
| control-plane-api | direct | 2/2 | Running | ghcr.io/stoa-platform/control-plane-api:latest |
| control-plane-ui | transitive | 1/1 | Running | ghcr.io/stoa-platform/control-plane-ui:latest |

If kubectl is unavailable, skip enrichment and note: "kubectl not available — showing static graph only."

### 5. Summary

Output a one-line blast radius summary:

```
Blast radius: N services impacted (X direct, Y transitive) across Z types
```

## Modes

| Command | Output |
|---------|--------|
| `/impact <service>` | Full analysis (table + graph + live enrichment) |
| `/impact <service> --static` | Skip kubectl enrichment (graph only) |

## Rules

- **Read-only** — never modify any service or infrastructure
- **No IPs** — never display IP addresses in output
- **No secrets** — never display secret values
- **Graceful degradation** — if kubectl fails, fall back to static graph
- **Catalog is source of truth** — live state enriches but doesn't replace catalog data
