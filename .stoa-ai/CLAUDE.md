# STOA Platform — Claude Code Context

> Ce fichier est le contexte persistant pour Claude Code. À lire au début de chaque session.

## 🎯 Projet

**STOA Platform** — "The European Agent Gateway"
- API Management AI-Native Open Source
- Positioning: "Legacy-to-MCP Bridge" — Pont entre APIs legacy et AI agents
- Kill feature: UAC (Universal API Contract) — "Define Once, Expose Everywhere"
- Licence: Apache 2.0 + Trademark protection

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CONTROL PLANE (Cloud)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Portal  │  │ Console  │  │   API    │  │ Keycloak │        │
│  │  (React) │  │  (React) │  │(FastAPI) │  │  (Auth)  │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              │
                    Config + Policies + Metrics
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA PLANE (On-Premise)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │   MCP    │  │webMethods│  │  Kong/   │                      │
│  │ Gateway  │  │ Gateway  │  │  Envoy   │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Structure Repo

```
stoa/
├── backend/                 # FastAPI Control Plane API
│   ├── app/
│   │   ├── api/v1/         # Endpoints REST
│   │   ├── core/           # Config, Security, Database
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   └── services/       # Business logic
│   └── tests/
├── frontend/
│   ├── portal/             # React Portal (catalogue, souscriptions)
│   └── console/            # React Console (admin, config)
├── mcp-gateway/            # MCP Gateway (Rust/Python)
├── infra/
│   ├── kubernetes/         # K8s manifests
│   ├── terraform/          # IaC
│   └── docker/             # Dockerfiles
└── docs/                   # Docusaurus documentation
```

## 🚫 Zones Interdites (NE PAS MODIFIER)

Ces fichiers sont stables et critiques. Ne pas toucher sans validation explicite :

- `backend/app/core/security.py` — Authentication/Authorization
- `backend/app/core/config.py` — Configuration centrale
- `infra/terraform/` — Infrastructure as Code
- `infra/kubernetes/production/` — Configs prod
- `.github/workflows/` — CI/CD pipelines

## ✅ Conventions de Code

### Python (Backend)
- **Style**: Black + isort + ruff
- **Types**: Toujours typer les fonctions
- **Tests**: pytest, coverage > 80%
- **Async**: Préférer async/await

### TypeScript/React (Frontend)
- **Style**: Prettier + ESLint
- **Components**: Functional + hooks
- **State**: Zustand ou React Query
- **Tests**: Vitest + Testing Library

### Commits
```
type(scope): description

Types: feat, fix, docs, style, refactor, test, chore
Scope: backend, portal, console, gateway, infra, docs
```

## 🔐 Sécurité

- **Zero Trust**: Tout trafic authentifié
- **RBAC**: Scopes OAuth2 granulaires
- **Secrets**: Jamais en clair, toujours Vault/env
- **Anonymisation**: Jamais de vrais noms clients dans le code/tickets

## 📊 Observabilité

- **Metrics**: Prometheus → Grafana
- **Logs**: Loki (structured JSON)
- **Traces**: OpenTelemetry (optionnel)
- **Alerts**: Alertmanager → Slack

## 🔄 Workflow Claude Code

1. **Lire ce fichier** au début de chaque session
2. **Lire plan.md** pour connaître la phase en cours
3. **Lire memory.md** pour l'état de la session précédente
4. **Coder → Tester → Commiter** en boucle
5. **Mettre à jour memory.md** avant `/clear`
6. **Notifier Slack** si bloqué ou phase terminée

## 🏷️ Labels & Priorities

| Priority | Signification |
|----------|---------------|
| P0 | Urgent — Cette semaine |
| P1 | High — Ce cycle |
| P2 | Medium — Ce mois |
| P3 | Low — Backlog |

## 📅 Dates Clés

- **MVP Demo**: 24 février 2026
- **"ESB is Dead" Presentation**: 24 février 2026
- **Free Run Until**: ~11 février 2026

# CLAUDE.md

Webhook notifications: https://hlfh.app.n8n.cloud/webhook/stoa-notify

Quand tu finis une tâche importante, notifie via:
curl -X POST "URL_CI_DESSUS" -H "Content-Type: application/json" -d '{"message": "ton message"}'
---

*Dernière mise à jour: 2026-02-04*
