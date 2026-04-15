# webMethods Gateway — Multi-Environment Architecture

## Overview

webMethods API Gateway instances bridged to the STOA Control Plane via **stoa-connect** agents.
stoa-connect is a pull-based Go agent — it connects outbound to the CP, the CP never calls back.
No DNS needed for the agent itself; only for the webMethods admin UI (Caddy TLS).

```
                    CONTROL PLANE (OVH MKS)
                    ┌─────────────────────┐
                    │  control-plane-api   │
                    │  (api.gostoa.dev)    │
                    └──────────▲──────────┘
                               │ Agent pulls routes/policies
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────┴──────┐  ┌─────┴────────┐  ┌────┴───────────┐
    │   PRODUCTION   │  │     DEV      │  │   (future)     │
    │  OVH VPS       │  │ Contabo w3   │  │   STAGING      │
    │<WEBMETHODS_VPS_IP>│  │<WORKER_3_IP> │  │                │
    └────────────────┘  └──────────────┘  └────────────────┘
```

## Environments

| Env | VPS | IP | wM Admin | stoa-connect | Caddy subdomain |
|-----|-----|----|----------|-------------|-----------------|
| **prod** | OVH webmethods-vps | `<WEBMETHODS_VPS_IP>` | `:5555` | `:8090` (systemd) | `webmethods.gostoa.dev` |
| **dev** | Contabo worker-3 | `<WORKER_3_IP>` | `:5555` (localhost) | `:8090` (systemd) | `dev-wm.gostoa.dev` |

## How stoa-connect works

The agent runs 4 background loops — all **outbound** to `api.gostoa.dev`:

| Loop | Interval | Direction | What |
|------|----------|-----------|------|
| Heartbeat | 30s | Agent → CP | `POST /v1/internal/gateways/{id}/heartbeat` |
| Discovery | 60s | Agent → local wM → CP | Queries wM `:5555`, reports to CP |
| Route sync | 30s | CP → Agent → local wM | Pulls routes from CP, pushes to wM |
| Policy sync | 60s | CP → Agent → local wM | Pulls policies from CP, applies to wM |

The CP sync engine **skips** `self_register` gateways (agent-managed).

## DNS Records (Cloudflare, DNS-only)

Convention: `vps-{gw}[-service].gostoa.dev` — see `stoa-infra/docs/carto/dns-inventory.md`.

| Subdomain | IP | Purpose |
|-----------|-----|---------|
| `vps-wm.gostoa.dev` | `<WEBMETHODS_VPS_IP>` | Prod wM admin (5555) |
| `vps-wm-ui.gostoa.dev` | `<WEBMETHODS_VPS_IP>` | Prod wM UI (9072) |
| `vps-wm-link.gostoa.dev` | `<WEBMETHODS_VPS_IP>` | Prod stoa-gateway sidecar (9200) |
| `dev-wm.gostoa.dev` | `<WORKER_3_IP>` | Dev wM admin |

## Services per VPS

### Production — OVH (`<WEBMETHODS_VPS_IP>`)

| Service | Container/Unit | Port |
|---------|---------------|------|
| webMethods API GW | `webmethods-apigateway` | `5555` |
| Elasticsearch | `webmethods-elasticsearch` | internal |
| stoa-connect | `stoa-connect.service` | `8090` |
| stoa-link | `stoa-link` (Docker) | `9200` |
| Caddy | `caddy.service` | `80/443` |

### Dev — Contabo worker-3 (`<WORKER_3_IP>`)

| Service | Container/Unit | Port |
|---------|---------------|------|
| webMethods API GW | `wm-dev-apigateway` | `5555` (localhost) |
| Elasticsearch | `wm-dev-elasticsearch` | internal |
| stoa-connect | `stoa-connect-dev.service` | `8090` |
| Caddy | `caddy.service` | `80/443` |
| HEGEMON agent | `hegemon-agent.service` | — |

## Files (this directory)

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Prod stack (OVH) |
| `docker-compose.dev.yml` | Dev stack (Contabo worker-3) |
| `Caddyfile` | Prod TLS (OVH) |
| `README.md` | This file |

Canonical copies on VPS:
- Prod: `/opt/webmethods/docker-compose.yml`, `/etc/caddy/Caddyfile`
- Dev: `/opt/webmethods-dev/docker-compose.yml`, `/etc/caddy/Caddyfile`

## Operations

```bash
# Verify health
curl -sf -u Administrator:manage https://webmethods.gostoa.dev/rest/apigateway/health  # prod
curl -sf -u Administrator:manage https://dev-wm.gostoa.dev/rest/apigateway/health      # dev

# SSH
ssh -i ~/.ssh/id_ed25519_stoa debian@<WEBMETHODS_VPS_IP>      # prod (OVH)
ssh -i ~/.ssh/id_ed25519_stoa hegemon@<WORKER_3_IP>          # dev (Contabo)

# Restart
# Prod: cd /opt/webmethods && sudo docker compose restart apigateway
# Dev:  cd /opt/webmethods-dev && sudo docker compose restart apigateway
```

## Trial keepalive

webMethods trial license expires every ~25 min. Cron restarts unhealthy containers:
- Prod: `*/25 * * * * /usr/local/bin/webmethods-keepalive.sh` (debian crontab)
- Dev: `*/25 * * * * /usr/local/bin/wm-dev-keepalive.sh` (hegemon crontab)
