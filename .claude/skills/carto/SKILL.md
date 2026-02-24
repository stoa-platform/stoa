# /carto — Platform Service Catalog

> Query the STOA platform service catalog for live infrastructure state.

## Modes

| Command | What it does |
|---------|-------------|
| `/carto` or `/carto all` | Full inventory — all services with deploy status |
| `/carto <service>` | Detail view of a single service + live state |
| `/carto drift` | Run drift detection (catalog vs K8s live) |
| `/carto graph` | Show the Mermaid dependency graph |
| `/carto secrets` | Show secrets-to-services mapping |

## Step 1: Read the Catalog

Read `docs/platform-catalog.yaml` — this is the source of truth for all services.

## Step 2: Execute Based on Mode

### Mode: `all` (default)

1. Read the full catalog
2. For each service, format a summary line:

```
## Platform Inventory — {metadata.lastUpdated}

### Core Services (K8s)
| Service | Type | Port | Prod Replicas | Health | ArgoCD |
|---------|------|------|---------------|--------|--------|
| control-plane-api | backend | 8000 | 2 | /health | control-plane-api |
| ... | ... | ... | ... | ... | ... |

### External Services (VPS)
| Service | Type | Host | Purpose |
|---------|------|------|---------|

### Clusters
| Cluster | Provider | Nodes |
|---------|----------|-------|
```

3. If kubectl is available, enrich with live status:
```bash
kubectl get deployments -n stoa-system -o custom-columns='NAME:.metadata.name,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image' 2>/dev/null
```

### Mode: `<service>` (single service detail)

1. Find the service in the catalog by name
2. Display all fields:

```
## {displayName} ({name})

Type: {type}
Tech: {tech}
Path: {path}
Port: {containerPort}
Image: {image}

### Deploy
- Prod: {deploy.prod.cluster}/{deploy.prod.namespace} ({deploy.prod.replicas} replicas)
- Staging: {deploy.staging...}

### Dependencies
- Depends on: {dependsOn[]}
- Consumed by: {exposedTo[]}

### Secrets
- {consumesSecrets[]}

### Health & Observability
- Health: {health}
- Metrics: {metrics}
- ArgoCD: {argocdApp}
- CI: {ciWorkflow}
```

3. If kubectl is available, add live state:
```bash
kubectl get deployment {k8sName} -n {namespace} -o json 2>/dev/null
kubectl get pods -l app={k8sName} -n {namespace} -o wide 2>/dev/null
```

4. If the service has an argocdApp, check sync status:
```bash
kubectl get application {argocdApp} -n argocd -o custom-columns='SYNC:.status.sync.status,HEALTH:.status.health.status' 2>/dev/null
```

### Mode: `drift`

Run the drift detection script:
```bash
./scripts/ops/catalog-sync.sh
```

Present results to the user with context about what each drift means.

### Mode: `graph`

1. Read `docs/architecture-graph.md`
2. Display the Mermaid graph and summary tables
3. If the file is missing, regenerate:
```bash
./scripts/ops/catalog-graph.sh
```

### Mode: `secrets`

Extract secrets mapping from the catalog:

```
## Secrets → Services Mapping

| Secret | Used By | Service Type |
|--------|---------|-------------|
| DATABASE_PASSWORD | control-plane-api | backend |
| KEYCLOAK_CLIENT_SECRET | control-plane-api | backend |
| KEYCLOAK_ADMIN_PASSWORD | stoa-gateway, keycloak | gateway, identity |
| ...
```

Flag any secret used by 0 or 3+ services as a potential concern.

## Step 3: Output

Format output as a clean markdown table. Keep it concise — the catalog YAML has all details, the skill surfaces the most useful information at a glance.

## Rules

- NEVER display IP addresses, even if kubectl returns them — mask with `<redacted>`
- NEVER display secret values — only secret names
- If kubectl is not available, show catalog data only (no error, just note "live state unavailable")
- Always show the catalog `lastUpdated` date so the user knows freshness
- If a service is missing from the catalog but visible in K8s, suggest adding it
