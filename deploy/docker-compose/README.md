# STOA Platform - Quick Start

Launch the STOA Platform in under 5 minutes with Docker Compose.

## Prerequisites

- **Docker Desktop 4.x+** with at least **8GB RAM** allocated
- **docker compose v2.x+** (check with `docker compose version`)
- **Free ports**: 3000, 3001, 5432, 8000, 8080, 9090

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/gostoa/stoa-platform.git
cd stoa-platform/deploy/docker-compose

# 2. Copy environment file
cp .env.example .env

# 3. Start all services
docker compose up -d

# 4. Wait for services to be ready (~3-4 minutes)
docker compose logs -f
```

Once you see `stoa-api` reporting healthy, the platform is ready!

## Access the Platform

| Service | URL | Credentials |
|---------|-----|-------------|
| **Console** | http://localhost:3000 | halliday / readyplayerone |
| **Keycloak** | http://localhost:8080 | admin / admin |
| **Grafana** | http://localhost:3001 | admin / admin |
| **API Docs** | http://localhost:8000/docs | - |

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

## What's Included

### Services (6 total, ~1.5GB RAM)

1. **PostgreSQL 15** - Database
2. **Keycloak 23.0** - Authentication with OASIS-themed users
3. **Control Plane API** - FastAPI backend with metrics
4. **Console UI** - React admin interface
5. **Prometheus** - Metrics collection
6. **Grafana** - Pre-configured dashboards

### Demo Data

- 3 tenants: Gregarious Games, OASIS Gunters, IOI Sixers
- 7 users with different roles (admin, tenant-admin, devops, viewer)
- Pre-configured Keycloak realm with OIDC clients

## Verify It Works

1. Open **Console**: http://localhost:3000
2. Login with `halliday` / `readyplayerone`
3. Explore the dashboard
4. Open **Grafana**: http://localhost:3001 (admin/admin)
5. Check the STOA Platform Overview dashboard

## Common Commands

```bash
# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f control-plane-api

# Check service status
docker compose ps

# Stop all services
docker compose stop

# Start all services
docker compose start

# Reset everything (destroy all data)
docker compose down -v
docker compose up -d
```

## Troubleshooting

### Port Conflicts

If you have port conflicts, edit `.env` to change the ports:

```env
PORT_CONSOLE=3002      # Change Console port
PORT_KEYCLOAK=8081     # Change Keycloak port
```

### Keycloak Takes Long to Start

Keycloak needs 60-90 seconds to start and import the realm. This is normal.

```bash
# Watch Keycloak startup
docker compose logs -f keycloak
```

### API Can't Connect to Keycloak

Wait for Keycloak to be fully ready before accessing the API:

```bash
# Check Keycloak health
curl http://localhost:8080/health/ready
```

### Database Migration Errors

If migrations fail, reset the database:

```bash
docker compose down -v
docker compose up -d
```

### Checking Service Health

```bash
# All services
docker compose ps

# API health
curl http://localhost:8000/health

# Keycloak health
curl http://localhost:8080/health/ready
```

## Architecture

```
                    +----------------+
                    |   PostgreSQL   |
                    |    (5432)      |
                    +--------+-------+
                             |
            +----------------+----------------+
            |                                 |
    +-------v-------+                +--------v-------+
    |   Keycloak    |                | Control Plane  |
    |    (8080)     |                |     API        |
    |               |                |    (8000)      |
    +-------+-------+                +--------+-------+
            |                                 |
            |                         +-------v-------+
            |                         |    Console    |
            +------------------------>|     UI        |
                                      |    (3000)     |
                                      +---------------+

    +---------------+                +---------------+
    |  Prometheus   |--------------->|    Grafana    |
    |    (9090)     |                |    (3001)     |
    +---------------+                +---------------+
```

## Full Stack (Optional)

For the full stack with Portal, MCP Gateway, and Loki (requires 16GB RAM):

```bash
docker compose --profile full up -d
```

## Next Steps

1. **Create a Tenant**: Login as `halliday` and create a new tenant
2. **Add APIs**: Register APIs in the catalog
3. **Invite Users**: Add users to your tenant
4. **Explore Grafana**: Check metrics and dashboards

## Support

- **Documentation**: https://docs.gostoa.dev
- **Issues**: https://github.com/gostoa/stoa-platform/issues
- **Discussions**: https://github.com/gostoa/stoa-platform/discussions

---

Built with the OASIS spirit - _Ready Player One_ theme data included!
