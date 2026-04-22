# STOA Demo Scripts

Scripts for the "ESB is Dead, AI Agents Are Here" live demo (24 fev 2026).

## Prerequisites

- Docker Compose stack running: `docker compose -f deploy/docker-compose/docker-compose.yml up -d`
- Python 3.11+ with `httpx` (`pip install httpx`)
- `ANORAK_PASSWORD` env var for API seeding

## Scripts

| Script | Purpose | Duration |
|--------|---------|----------|
| `seed-all.sh` | Master orchestrator — seeds all demo data | ~2 min |
| `seed-error-snapshot.py` | Seed error snapshots into OpenSearch | ~10s |
| `traffic-generator.py` | Generate realistic API traffic | configurable |
| `check-health.sh` | Verify all Docker Compose services are healthy | ~5s |
| `test-opensearch.sh` | Verify OpenSearch pipeline end-to-end | ~15s |
| `opensearch-live-demo.sh` | 2-min presenter-friendly error correlation demo | ~90s |
| `reset-demo.sh` | Idempotent harness — invokes cp-api demo reset (CAB-2149 contract) | ~10s |
| `pre-demo-check.sh` | Binary preflight gate (health + seed + audience claim + tenant count) | ~5s |
| `demo-dry-run.sh` | Cold full-path dry-run; emits timestamped artifacts under `docs/audits/demo-dryrun-<UTC>/` | ~20s |

## Demo Harness Runbook (CAB-2148)

Invocation sequence for a cold demo rehearsal:

```bash
export STOA_API_URL="https://api.gostoa.dev"
export STOA_GATEWAY_URL="https://mcp.gostoa.dev"
export STOA_API_TOKEN="..."         # demo-admin bearer
export STOA_DEMO_MIN_TENANTS=4      # optional, default 4

# Full cold run (reset + preflight) with evidence capture
./scripts/demo/demo-dry-run.sh

# Or step by step:
./scripts/demo/reset-demo.sh
./scripts/demo/pre-demo-check.sh
```

Exit-code contract (binary, no warning state):

| Script | Exit 0 means |
|--------|--------------|
| `reset-demo.sh` | cp-api returned `status=reset_complete` — reset fully applied |
| `pre-demo-check.sh` | every check passed (any FAIL = exit 1) |
| `demo-dry-run.sh` | reset (unless `--skip-reset`) AND preflight passed; artifacts written |

Artifact archive (`demo-dry-run.sh` only): `docs/audits/demo-dryrun-<UTC>/` contains `summary.md`, `metadata.json`, and per-step logs. Commit the archive as evidence per the repo audit rule.

**Contract dependency**: `reset-demo.sh` and the seed-state probe in `pre-demo-check.sh` assume the cp-api endpoints delivered by CAB-2149 (`POST /api/v1/demo/reset`, `GET /api/v1/demo/status`). Until CAB-2149 merges, the scripts will fail fast with a non-zero exit and a diagnostic on stderr — that is the intended behavior.

## Quick Start

```bash
# 1. Start the stack
cd deploy/docker-compose && docker compose up -d

# 2. Wait for services
./scripts/demo/check-health.sh --wait

# 3. Seed all demo data
./scripts/demo/seed-all.sh

# 4. Verify OpenSearch pipeline
./scripts/demo/test-opensearch.sh

# 5. Run live demo
./scripts/demo/opensearch-live-demo.sh
```

## Makefile Targets

```bash
make demo-opensearch-seed   # Seed OpenSearch only
make demo-opensearch-test   # Verify OpenSearch pipeline
make demo-opensearch-live   # Run 2-min live demo
make demo-federation-live   # Run 2-min federation demo
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSEARCH_URL` | `https://localhost:9200` | OpenSearch endpoint |
| `OPENSEARCH_AUTH` | `admin:$OPENSEARCH_ADMIN_PASSWORD` | OpenSearch credentials (prod: from Infisical) |
| `GRAFANA_URL` | `http://localhost:3001` | Grafana endpoint |
| `CONTROL_PLANE_URL` | `http://localhost:8000` | Control Plane API |
| `KEYCLOAK_URL` | `http://localhost:8080` | Keycloak endpoint |
| `ANORAK_PASSWORD` | _(required)_ | Admin password for API seeding |
| `ERROR_COUNT` | `50` | Number of error snapshots to seed |
| `TRAFFIC_DURATION` | `60` | Traffic generator duration (seconds) |

## Known Issues

- **OpenSearch cold start**: First boot takes 30-60s. Use `check-health.sh --wait`.
- **Self-signed certs**: OpenSearch uses self-signed TLS. Scripts use `-k` (insecure) flag.
- **Default password**: OpenSearch admin password for local dev defaults to `admin:admin` after security init. Production password is in Infisical (`prod/opensearch/ADMIN_PASSWORD`).
- **Grafana datasource**: Provisioned automatically via `deploy/docker-compose/config/grafana/provisioning/`.
