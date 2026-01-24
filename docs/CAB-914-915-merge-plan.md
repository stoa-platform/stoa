# Plan de Merge: apim-aws → stoa-quickstart

## Contexte

| Repo Source | Repo Cible |
|-------------|------------|
| `/Users/torpedo/apim-aws` | `stoa-platform/stoa-quickstart` |

**Tickets concernés:**
- **CAB-914**: Docker-Compose Quick Start + Demo Environment
- **CAB-915**: MCP Gateway (ticket séparé)

---

## Vue d'Ensemble des Repos

### apim-aws (Source)
Production-ready platform avec:
- MCP Gateway complet (Python/FastAPI)
- 10+ dashboards Grafana
- Tests E2E, Load, Chaos, Security
- OPA Policy Engine
- Kafka/Redpanda metering
- 10 migrations Alembic
- Ready Player One demo data

### stoa-quickstart (Cible - État Actuel)
Quick start local avec:
- 11 services Docker Compose
- 3 dashboards Grafana (créés CAB-914)
- Metrics simulator (créé CAB-914)
- OASIS demo data (créé CAB-914)
- Keycloak avec 6 users

---

## Stratégie de Merge

### Principe Directeur
> **stoa-quickstart reste simple** - on copie sélectivement, pas tout.

### Priorisation

| Priorité | Composant | Justification |
|----------|-----------|---------------|
| P0 | MCP Gateway | Core feature (CAB-915) |
| P1 | Tests Load (K6) | Validation perf |
| P1 | Dashboards avancés | Meilleure observabilité |
| P2 | OPA Policies | Security (optionnel) |
| P3 | Tests E2E | Qualité |
| P4 | Chaos tests | Kubernetes only |

---

## Phase 1: MCP Gateway (CAB-915)

### Source
```
apim-aws/mcp-gateway/
├── src/
│   ├── main.py (1057 lines)
│   ├── config/
│   ├── handlers/
│   │   ├── mcp.py
│   │   ├── mcp_sse.py
│   │   └── subscriptions.py
│   ├── models/
│   ├── services/
│   │   ├── tool_handlers.py (33KB)
│   │   ├── openapi_converter.py
│   │   └── tool_registry/
│   ├── middleware/
│   │   └── metrics.py
│   └── policy/
│       ├── opa_client.py
│       └── policies/
├── Dockerfile
├── Dockerfile.dev
├── requirements.txt
└── pyproject.toml
```

### Cible
```
stoa-quickstart/mcp-gateway/
├── src/                    # Copie directe
├── Dockerfile              # Adapter pour quickstart
├── requirements.txt        # Simplifier (sans kafka)
└── pyproject.toml
```

### Modifications Requises

1. **Désactiver Kafka metering** (pas de Redpanda en quickstart)
   ```python
   # config/settings.py
   METERING_ENABLED = False
   ```

2. **OPA en mode embedded** (pas de sidecar)
   ```python
   OPA_EMBEDDED = True
   OPA_URL = None  # Pas de sidecar
   ```

3. **docker-compose.yml** - Ajouter service:
   ```yaml
   mcp-gateway:
     build: ./mcp-gateway
     ports:
       - "8082:8080"
     environment:
       KEYCLOAK_URL: http://keycloak:8080
       STOA_DATABASE_URL: postgresql+asyncpg://stoa:stoa-quickstart-secret@postgres:5432/stoa
       OPA_EMBEDDED: "true"
       METERING_ENABLED: "false"
     depends_on:
       control-plane:
         condition: service_healthy
   ```

### Estimé: 1 jour

---

## Phase 2: Tests Load (K6)

### Source
```
apim-aws/tests/load/
├── docker-compose.yml      # K6 + InfluxDB + Grafana
├── k6/
│   ├── scenarios/
│   │   ├── smoke.js        # 5 VUs, 30s
│   │   ├── load.js         # 100 VUs, 5min
│   │   ├── stress.js       # 500 VUs, 10min
│   │   └── spike.js        # 1000 VUs spike
│   ├── lib/
│   │   ├── config.js
│   │   ├── auth.js
│   │   └── checks.js
│   └── thresholds.js       # SLO definitions
└── grafana/
    └── dashboards/         # K6 dashboard
```

### Cible
```
stoa-quickstart/tests/
├── load/
│   ├── docker-compose.yml  # Adapter URLs localhost
│   ├── k6/                 # Copie directe
│   └── grafana/            # Copie directe
└── README.md               # Instructions
```

### Modifications Requises

1. **config.js** - Adapter endpoints:
   ```javascript
   export const getEnv = () => ({
     baseUrl: __ENV.BASE_URL || 'http://host.docker.internal:8080',
     mcpUrl: __ENV.MCP_URL || 'http://host.docker.internal:8082',
     gatewayUrl: __ENV.GATEWAY_URL || 'http://host.docker.internal:8080',
   });
   ```

2. **auth.js** - Keycloak localhost:8081

### Estimé: 0.5 jour

---

## Phase 3: Dashboards Avancés

### Source
```
apim-aws/docker/observability/grafana/dashboards/
├── mcp-gateway.json
├── control-plane-api.json
├── platform-overview.json
├── slo-dashboard.json
└── error-tracking.json
```

### Cible
```
stoa-quickstart/observability/grafana/dashboards/
├── stoa-overview.json      # GARDER (créé CAB-914)
├── api-traffic.json        # GARDER
├── system-health.json      # GARDER
├── mcp-gateway.json        # AJOUTER
├── slo-dashboard.json      # AJOUTER
└── error-tracking.json     # AJOUTER
```

### Modifications Requises
- Adapter datasources (`prometheus` → `Prometheus`)
- Vérifier UIDs des datasources

### Estimé: 0.25 jour

---

## Phase 4: OPA Policies (Optionnel)

### Source
```
apim-aws/mcp-gateway/src/policy/
├── opa_client.py
├── scopes.py
├── argument_engine.py
└── policies/
    ├── authz.rego
    └── tools.rego
```

### Décision
**Inclure en mode embedded** - Pas de service OPA séparé, mais policies embarquées dans MCP Gateway.

---

## Fichiers à NE PAS Copier

| Fichier/Dossier | Raison |
|-----------------|--------|
| `deploy/` | Kubernetes-specific |
| `tests/chaos/` | Requires K8s |
| `tests/security/` | Pentest avancé |
| `metering/` | Kafka dependency |
| `k8s/` | CRD watchers |
| `features/error_snapshots/` | Complexité (phase 2) |

---

## Checklist de Merge

### CAB-914 (Quick Start) - FAIT
- [x] Observability stack (Prometheus, Grafana, Loki)
- [x] 3 dashboards Grafana
- [x] Metrics simulator
- [x] OASIS demo data (tenants + APIs)
- [x] Keycloak OASIS users
- [x] README enrichi

### CAB-915 (MCP Gateway)
- [ ] Copier mcp-gateway/src/
- [ ] Créer Dockerfile quickstart
- [ ] Adapter requirements.txt
- [ ] Ajouter service docker-compose
- [ ] Tester endpoints MCP
- [ ] Dashboard mcp-gateway.json

### Tests
- [ ] Copier tests/load/k6/
- [ ] Adapter config pour localhost
- [ ] Créer README tests
- [ ] Valider smoke test

---

## Commandes de Merge

```bash
# 1. MCP Gateway
cp -r /Users/torpedo/apim-aws/mcp-gateway/src stoa-quickstart/mcp-gateway/
cp /Users/torpedo/apim-aws/mcp-gateway/requirements.txt stoa-quickstart/mcp-gateway/
# Adapter manuellement Dockerfile et config

# 2. Tests Load
mkdir -p stoa-quickstart/tests/load
cp -r /Users/torpedo/apim-aws/tests/load/k6 stoa-quickstart/tests/load/
cp /Users/torpedo/apim-aws/tests/load/docker-compose.yml stoa-quickstart/tests/load/

# 3. Dashboards
cp /Users/torpedo/apim-aws/docker/observability/grafana/dashboards/mcp-gateway.json \
   stoa-quickstart/observability/grafana/dashboards/
cp /Users/torpedo/apim-aws/docker/observability/grafana/dashboards/slo-dashboard.json \
   stoa-quickstart/observability/grafana/dashboards/
```

---

## Dépendances

```mermaid
graph LR
    A[CAB-914 Quick Start] --> B[CAB-915 MCP Gateway]
    B --> C[Tests Load]
    B --> D[Dashboards MCP]
    C --> E[Benchmarks]
```

---

## Estimés

| Phase | Effort | Dépendance |
|-------|--------|------------|
| Phase 1: MCP Gateway | 1 jour | CAB-914 |
| Phase 2: Tests Load | 0.5 jour | Phase 1 |
| Phase 3: Dashboards | 0.25 jour | Phase 1 |
| Phase 4: OPA | 0.25 jour | Phase 1 |
| **Total CAB-915** | **2 jours** | |

---

## Risques

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Port conflicts (8080) | Medium | MCP Gateway sur 8082 |
| Memory footprint | High | Documenter 6GB min |
| Keycloak client | Low | Realm déjà configuré |
| OPA policies | Medium | Mode embedded |
