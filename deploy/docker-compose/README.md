# STOA Platform - Quick Start

Launch the STOA Platform in under 5 minutes with Docker Compose.

## Prerequisites

- **Docker Desktop 4.x+** with at least **8GB RAM** allocated
- **docker compose v2.x+** (check with `docker compose version`)
- **Free ports**: 80, 3002, 5432, 8000, 8080, 8081, 9090, 9093, 9200, 5601

## Quick Start

```bash
# 1. Navigate to docker-compose directory
cd deploy/docker-compose

# 2. Copy environment file
cp .env.example .env

# 3. Start all services
docker compose up -d

# 4. Wait for services to be ready (~3-4 minutes)
../../scripts/demo/check-health.sh --wait

# 5. (Optional) Seed demo data
../../scripts/demo/seed-all.sh --skip-traffic
```

## Access the Platform

All services are accessible through the nginx reverse proxy on port 80:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Console** | http://localhost | halliday / readyplayerone |
| **Portal** | http://localhost/portal | (self-registration) |
| **API Docs** | http://localhost/api/docs | - |
| **Keycloak** | http://localhost/auth | admin / admin |
| **Grafana** | http://localhost/grafana | admin / admin |
| **STOA Logs** | http://localhost/logs | admin / StOa_Admin_2026! |
| **Prometheus** | http://localhost:9090 | - |
| **AlertManager** | http://localhost:9093 | - |
| **Rust Gateway** | http://localhost/gateway/health | - |

Direct access (bypassing proxy):

| Service | URL |
|---------|-----|
| Console | http://localhost:3000 |
| Portal | http://localhost:3002 |
| API | http://localhost:8000 |
| Gateway | http://localhost:8081 |
| Keycloak | http://localhost:8080 |
| Grafana | http://localhost:3001 |
| OpenSearch | https://localhost:9200 |
| OpenSearch Dashboards | http://localhost:5601 |

## Services (17 base)

| # | Service | Image | Purpose |
|---|---------|-------|---------|
| 1 | PostgreSQL 15 | postgres:15-alpine | Database |
| 2 | Keycloak 23.0 | quay.io/keycloak/keycloak:23.0 | Authentication + 5 federation realms |
| 3 | DB Migrate | control-plane-api:1.0.0 | Alembic migrations (one-shot) |
| 4 | Control Plane API | control-plane-api:1.0.0 | FastAPI backend |
| 5 | Console UI | control-plane-ui:1.0.0 | React admin interface |
| 6 | Portal | portal:1.0.0 | Developer portal |
| 7 | Rust Gateway | stoa-gateway (local build) | API gateway (edge-mcp mode) |
| 8 | Nginx | nginx:1.25-alpine | Reverse proxy |
| 9 | Prometheus | prom/prometheus:v2.48.0 | Metrics |
| 10 | Grafana | grafana/grafana:10.2.2 | Dashboards (12 pre-configured) |
| 11 | Loki | grafana/loki:2.9.3 | Log aggregation |
| 12 | Promtail | grafana/promtail:2.9.3 | Log shipping |
| 13 | AlertManager | prom/alertmanager:v0.27.0 | Alert routing |
| 14 | OpenSearch | opensearch:2.11.0 | Search + error snapshots |
| 15 | OpenSearch Dashboards | opensearch-dashboards:2.11.0 | STOA Logs UI |
| 16 | OpenSearch Init | opensearch:2.11.0 | Security setup (one-shot) |

**RAM usage**: ~3GB (fits on 8GB machines)

## Optional Profiles

```bash
# Add federation services (OpenLDAP + Federation Gateway)
docker compose --profile federation up -d

# Add OIDC-protected Prometheus (requires OIDC setup first)
docker compose --profile monitoring-oidc up -d

# All profiles
docker compose --profile federation --profile monitoring-oidc up -d
```

| Profile | Services Added | Extra RAM |
|---------|---------------|-----------|
| `federation` | OpenLDAP, Federation Gateway | ~256MB |
| `monitoring-oidc` | oauth2-proxy | ~64MB |

## Demo Users (OASIS Theme)

| Username | Password | Role | Tenant |
|----------|----------|------|--------|
| halliday | readyplayerone | Platform Admin | Gregarious Games |
| morrow | ogdensmcguffin | Platform Admin | Gregarious Games |
| parzival | copperkeystart | Tenant Admin | OASIS Gunters |
| art3mis | samantha2045 | DevOps | OASIS Gunters |
| aech | helen2045 | Viewer | OASIS Gunters |
| sorrento | ioi101 | Tenant Admin | IOI Sixers |
| sixer42 | loyalty2045 | Viewer | IOI Sixers |

## Demo Data Seeding

```bash
# Seed everything (APIs, consumers, OpenSearch errors, traffic)
ANORAK_PASSWORD=readyplayerone ../../scripts/demo/seed-all.sh

# Seed only OpenSearch error snapshots
../../scripts/demo/seed-all.sh --opensearch-only

# Skip traffic generator
../../scripts/demo/seed-all.sh --skip-traffic

# Include federation isolation tests
../../scripts/demo/seed-all.sh --federation
```

## Common Commands

```bash
# Check health of all services
../../scripts/demo/check-health.sh

# Wait for all services to become healthy
../../scripts/demo/check-health.sh --wait

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f control-plane-api

# Stop all services
docker compose stop

# Reset everything (destroy all data)
docker compose down -v
docker compose up -d
```

## Troubleshooting

### Port Conflicts

Edit `.env` to change ports:

```env
PORT_CONSOLE=3003      # Change Console port
PORT_KEYCLOAK=8082     # Change Keycloak port
```

### Keycloak Takes Long to Start

Keycloak needs 60-90 seconds to start and import 6 realms. This is normal.

```bash
docker compose logs -f keycloak
```

### OpenSearch Won't Start

OpenSearch requires `vm.max_map_count >= 262144`:

```bash
# macOS: Docker Desktop handles this automatically
# Linux:
sudo sysctl -w vm.max_map_count=262144
```

### Rust Gateway Build Fails

The gateway builds from source. Ensure Rust toolchain is available or use cached layers:

```bash
# Rebuild gateway only
docker compose build stoa-gateway
docker compose up -d stoa-gateway
```

## Architecture

```
              ┌─────────────────────────────────────────────────────────┐
              │                  nginx (port 80)                        │
              │  /        /api   /auth  /portal /gateway /grafana /logs │
              └──┬────────┬──────┬──────┬───────┬───────┬────────┬─────┘
                 │        │      │      │       │       │        │
         Console UI    API   Keycloak Portal  Gateway Grafana  OS Dashboards
          (3000)     (8000)  (8080)  (3002)   (8081)  (3001)    (5601)
                       │      │                 │       │          │
                  PostgreSQL ──┘                 │  Prometheus   OpenSearch
                   (5432)                        │   (9090)      (9200)
                                                 │       │
                                            Loki ┘  AlertManager
                                           (3100)    (9093)
```

## Next Steps

1. **Create a Tenant**: Login as `halliday` and create a new tenant
2. **Seed Demo Data**: Run `seed-all.sh` for a fully populated platform
3. **Explore Grafana**: Check the 12 pre-configured dashboards
4. **Try the Gateway**: Send requests through `http://localhost/gateway/health`

## Support

- **Documentation**: https://docs.gostoa.dev
- **Issues**: https://github.com/stoa-platform/stoa/issues
