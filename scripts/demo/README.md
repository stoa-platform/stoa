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
