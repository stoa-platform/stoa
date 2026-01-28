# CLAUDE.md — STOA Platform Development Context

> **Version**: 2.0.0 | **Updated**: 2026-01-28 | **Author**: CAB Ingénierie
> 
> Ce fichier est le contexte système pour Claude Code CLI.
> Il définit les règles, la structure, et les processus de validation.

---

## 🎯 Mission

**STOA Platform** — The European Agent Gateway

Plateforme open-source de gestion d'APIs AI-native, alternative souveraine à Kong/Apigee.

**Philosophie** : "Define once, expose everywhere" via Universal API Contract (UAC).

### Core Components
- **Control Plane UI**: Console React pour API Providers (tenant/API management)
- **Portal**: Developer Portal React pour API Consumers (browse, subscribe, test)
- **Control Plane API**: FastAPI backend avec Keycloak auth
- **MCP Gateway**: AI-Native API access via MCP protocol (edge-mcp mode)
- **STOA Gateway**: Implementation Rust émergente (4 modes)

---

## 🚨 CRITICAL RULES — DO NOT VIOLATE

### Infrastructure Protection

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         🛑 NEVER DO THESE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ❌ NEVER run `terraform destroy` without explicit user confirmation        │
│  ❌ NEVER delete EKS clusters in production                                 │
│  ❌ NEVER delete GitLab repositories with production data                   │
│  ❌ NEVER delete Kafka topics with unprocessed events                       │
│  ❌ NEVER modify Keycloak realm without backup                              │
│  ❌ NEVER commit real secrets (passwords, API keys, tokens)                 │
│  ❌ NEVER push directly to main branch                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Safe Operations (Always OK)

| Command | Purpose |
|---------|---------|
| `terraform plan` | Preview infra changes |
| `helm diff` | Preview Helm changes |
| `kubectl get` | Read-only K8s operations |
| `git status/log/diff` | Git read operations |
| `docker build` | Local image build |

### Docker Build Requirements

```bash
# ⚠️ ALWAYS build multi-arch images for AMD64 + ARM64
# EKS runs on AMD64, local Mac uses ARM64

# ✅ CORRECT
docker buildx build --platform linux/amd64,linux/arm64 -t <image> --push .

# ❌ WRONG (single arch)
docker build -t <image> .
```

---

## 🛑 WORKFLOW OBLIGATOIRE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AVANT TOUTE MODIFICATION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. AUDIT        → Vérifier l'état actuel avant de modifier                │
│  2. PLAN         → Proposer un plan détaillé                                │
│  3. VALIDATION   → Faire valider par le Council (si > 13 pts)              │
│  4. EXECUTE      → Implémenter après approbation                           │
│  5. VERIFY       → Vérifier que tout fonctionne                            │
│                                                                             │
│  ⚠️ NE JAMAIS sauter les étapes 1-3 pour les changements importants        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quand demander validation Council ?

| Points | Action |
|--------|--------|
| < 5 pts | Exécuter directement |
| 5-13 pts | Proposer plan, attendre OK |
| > 13 pts (MEGA) | AUDIT + PLAN + Council obligatoire |

---

## 🏗️ Architecture des Repositories

**Pattern : ArgoCD / Cilium** — Code + Charts séparés (validé Council 2026-01-28)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STOA PLATFORM ECOSYSTEM                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PUBLIC (GitHub - stoa-platform org)                                        │
│  ├── stoa           → Code applicatif (API, UI, Portal, MCP Gateway)       │
│  ├── stoa-charts    → Helm charts publics → charts.gostoa.dev              │
│  └── stoa-docs      → Documentation Docusaurus → docs.gostoa.dev           │
│                                                                             │
│  PRIVATE (GitHub)                                                           │
│  ├── stoa-platform/stoa-web  → Landing page → gostoa.dev                   │
│  └── PotoMitan/stoa-infra    → Terraform + Ansible + ArgoCD values         │
│                                                                             │
│  DEPRECATED                                                                 │
│  └── PotoMitan/stoa-gitops   → Fusionné dans stoa-infra                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pourquoi ce pattern ?

| Raison | Explication |
|--------|-------------|
| **Standard OSS** | ArgoCD, Cilium, Prometheus utilisent ce pattern |
| **Cycles séparés** | Code change souvent, charts moins |
| **Contributeurs** | Devs sur `stoa`, Platform engineers sur `stoa-charts` |
| **Artifact Hub** | Découverte facilitée des charts |

### Structure de `stoa-platform/stoa` (PUBLIC)

```
stoa/
├── control-plane-api/        # Python 3.12 / FastAPI
│   ├── src/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── control-plane-ui/         # React — Console (API Provider)
│   ├── src/
│   └── package.json
│
├── portal/                   # React + Vite — Developer Portal (API Consumer)
│   ├── src/
│   └── package.json
│
├── mcp-gateway/              # Python/FastAPI — Edge-MCP mode (production)
│   ├── src/
│   ├── tests/
│   └── pyproject.toml
│
├── stoa-gateway/             # Rust/Tokio — Unified gateway (Q4 2026)
│   ├── src/
│   └── Cargo.toml
│
├── quickstart/               # Getting started
│   └── docker-compose.yaml
│
├── .github/workflows/        # CI/CD (tests, build images)
│
├── CLAUDE.md                 # ⭐ CE FICHIER
└── README.md
```

### Structure de `stoa-platform/stoa-charts` (PUBLIC)

```
stoa-charts/
├── charts/
│   ├── stoa-platform/        # Umbrella chart
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   ├── values-preview.yaml
│   │   └── templates/
│   ├── stoa-control-plane/   # Standalone Control Plane
│   ├── stoa-mcp-gateway/     # Standalone MCP Gateway
│   ├── stoa-portal/          # Standalone Portal
│   └── stoa-observability/   # Prometheus + Grafana + Loki
│
├── .github/workflows/
│   └── release.yml           # Lint, scan, publish to charts.gostoa.dev
│
└── README.md
```

### Structure de `stoa-platform/stoa-docs` (PUBLIC)

```
stoa-docs/
├── docs/
│   ├── getting-started/
│   ├── concepts/
│   ├── guides/
│   ├── api/
│   └── adr/                  # Architecture Decision Records
├── src/
│   └── components/
├── docusaurus.config.ts
└── package.json

→ Deployed: docs.gostoa.dev (Vercel)
```

### Structure de `stoa-platform/stoa-web` (PRIVATE)

```
stoa-web/
├── src/                      # Landing page gostoa.dev
├── public/
└── package.json

→ Deployed: gostoa.dev
```

### Structure de `PotoMitan/stoa-infra` (PRIVATE)

```
stoa-infra/
├── terraform/                # AWS EKS, VPC, RDS
│   ├── modules/
│   └── environments/
│       ├── dev/
│       ├── staging/
│       └── prod/
│
├── ansible/                  # Playbooks AWX
│   ├── playbooks/
│   └── roles/
│
├── deploy/                   # ArgoCD configs (ex stoa-gitops)
│   ├── argocd/               # Applications, ApplicationSets
│   ├── overlays/             # Kustomize per env
│   └── values/               # Helm values overrides per env
│
├── webmethods/               # Config gateway (ex stoa-gitops)
│   ├── apis/
│   ├── policies/
│   └── aliases/
│
└── .gitlab-ci.yml            # Schedules (sync, E2E, security)
```

---

## 🏛️ Council de Validation

Pour les tickets > 13 points ou les décisions architecturales :

| Persona | Rôle | Focus |
|---------|------|-------|
| **Chucky** | Security Lead | Secrets, CVE, rotation, least privilege |
| **N3m0** | DevSecOps | CI/CD security, supply chain, scanning |
| **Gh0st** | Platform Architect | Séquençage, dépendances, scalabilité |
| **Pr1nc3ss** | Compliance | RGPD, audit trail, data governance |
| **OSS Killer** | Skeptical VC | Business value, OSS viability |
| **Archi 50x50** | 40-year Architect | "Compréhensible en 30 secondes?" |
| **Better Call Saul** | Legal/IP | Licensing, trademark, anti-fork |

### Format de Soumission Council

```markdown
## 🏛️ Council Review Request

### Ticket: CAB-XXX
### Objectif (1 phrase): [...]
### Plan: [...]
### Estimation: XX points
### Questions pour le Council: [...]
```

---

## 🔧 STOA Gateway Architecture (ADR-024)

### 4 Deployment Modes

| Mode | Status | Protocol | Use Case |
|------|--------|----------|----------|
| **edge-mcp** | ✅ Production | MCP/SSE | Claude.ai, AI agents |
| **sidecar** | 🔜 Q2 2026 | HTTP | Behind Kong/Envoy/Apigee |
| **proxy** | 🔜 Q3 2026 | HTTP | Inline policy enforcement |
| **shadow** | ⏸️ Deferred | Passive | Traffic capture, UAC auto-gen |

### Current Implementation

- **Production**: Python/FastAPI (`mcp-gateway/`)
- **Target Q4 2026**: Rust/Tokio (`stoa-gateway/`)

### Edge-MCP Features (Phase 12)

- **Tool Registry**: Dynamic tool registration from CRDs
- **OPA Policy Engine**: Fine-grained RBAC
- **Metering Pipeline**: Kafka-based usage tracking
- **Kubernetes CRDs**: Tool and ToolSet resources

---

## 📊 Estimation et Vélocité

### Échelle de Points (Recalibrée 2026-01-28)

| Points | Temps réel | Exemple |
|--------|------------|---------|
| 1 | ~5 min | Fix typo |
| 2 | ~10 min | Add config |
| 5 | ~30 min | Feature complète |
| 8 | ~1h | Integration |
| 13 | ~1.5h | Nouveau module |
| 21+ | ~2-3h | MEGA (requires Council) |

### Vélocité Mesurée

- **Avec Claude AI** : ~8 points/heure
- **Sans AI** : ~1-2 points/heure

---

## 🔐 RBAC Roles

| Role | Scopes | Description |
|------|--------|-------------|
| `cpi-admin` | `stoa:admin` | Full platform access |
| `tenant-admin` | `stoa:write, stoa:read` | Manage own tenant |
| `devops` | `stoa:write, stoa:read` | Deploy and promote APIs |
| `viewer` | `stoa:read` | Read-only access |

---

## 💻 Common Tasks

### Development

```bash
# Console UI (API Provider)
cd control-plane-ui && npm install && npm start

# Developer Portal (API Consumer)
cd portal && npm install && npm run dev

# Control Plane API
cd control-plane-api && pip install -r requirements.txt && uvicorn src.main:app --reload

# MCP Gateway
cd mcp-gateway && pip install -e ".[dev,k8s]" && python -m src.main

# Run tests
cd mcp-gateway && pytest --cov=src
cd portal && npm run test

# Helm lint
helm lint charts/stoa-platform
```

### Deployment

```bash
# Terraform (⚠️ ALWAYS plan first)
cd terraform/environments/dev
terraform init && terraform plan
# Only after review:
terraform apply

# Helm
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system --create-namespace

# Apply CRDs
kubectl apply -f charts/stoa-platform/crds/
```

### MCP Gateway

```bash
# Register a tool via CRD
kubectl apply -f - <<EOF
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: my-api-tool
  namespace: tenant-acme
spec:
  displayName: My API Tool
  description: A sample tool
  endpoint: https://api.example.com/v1/action
  method: POST
EOF

# Check tool status
kubectl get tools -n tenant-acme
```

---

## 🌐 Key URLs

### Production

| Service | URL |
|---------|-----|
| Console UI (Provider) | https://console.gostoa.dev |
| Developer Portal | https://portal.gostoa.dev |
| Control Plane API | https://api.gostoa.dev |
| MCP Gateway | https://mcp.gostoa.dev |
| API Gateway Runtime | https://apis.gostoa.dev |
| Keycloak | https://auth.gostoa.dev |
| ArgoCD | https://argocd.gostoa.dev |
| Vault | https://vault.gostoa.dev |
| AWX | https://awx.gostoa.dev |

### Documentation

| Resource | URL |
|----------|-----|
| Docs | https://docs.gostoa.dev |
| Helm Charts | https://charts.gostoa.dev |
| GitHub | https://github.com/stoa-platform |
| Linear | https://linear.app/hlfh-workspace |

---

## 🚨 Patterns à Éviter

### ❌ Anti-Patterns

```yaml
# 1. Secrets en clair
password: "MyRealPassword123!"  # ❌ JAMAIS

# 2. Images sans tag
image: stoa-control-plane  # ❌ Toujours tag ou digest

# 3. Pas de resource limits
resources: {}  # ❌ Toujours définir

# 4. RunAsRoot
runAsUser: 0  # ❌ JAMAIS root

# 5. Single-arch build
docker build -t img .  # ❌ Toujours multi-arch
```

### ✅ Patterns Corrects

```yaml
# 1. Secrets via références
existingSecret: stoa-postgresql

# 2. Images avec tag
image:
  tag: "v1.2.3"

# 3. Resource limits
resources:
  limits:
    memory: "512Mi"
    cpu: "500m"

# 4. Non-root
runAsNonRoot: true
runAsUser: 1000

# 5. Multi-arch
docker buildx build --platform linux/amd64,linux/arm64 ...
```

---

## 🔧 Configuration

La plateforme utilise `BASE_DOMAIN` comme source unique pour toutes les URLs.

```bash
# Environment configs
deploy/config/dev.env
deploy/config/staging.env
deploy/config/prod.env
```

### MCP Gateway Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | Enable OPA policy engine |
| `OPA_EMBEDDED` | `true` | Use embedded evaluator |
| `METERING_ENABLED` | `true` | Enable Kafka metering |
| `K8S_WATCHER_ENABLED` | `false` | Enable CRD watcher |

---

## 📝 Templates

### Nouveau Ticket

```markdown
## 🎯 Objectif
[1 phrase]

## 🤔 Why Now
[Pourquoi maintenant]

## ✅ Definition of Done
- [ ] Critère 1
- [ ] Tests passent
- [ ] Docs à jour

## 📊 Estimation
[X] points
```

---

## 🧠 Context pour Claude

### Ce que Claude doit toujours faire

1. **AUDIT avant de modifier** — vérifier l'état actuel
2. **Proposer un PLAN** pour les changements > 5 pts
3. **Demander validation Council** pour MEGA-tickets (> 13 pts)
4. **Vérifier les ADRs** avant de proposer une architecture
5. **Utiliser l'échelle recalibrée** (8 pts/heure)

### Questions à poser si ambigu

- "Ce changement impacte-t-il les charts publics ou l'infra privée ?"
- "Faut-il un ADR pour cette décision ?"
- "Quel est le Why Now de ce ticket ?"
- "Souhaites-tu une validation Council avant ?"

---

## 📜 Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2026-01-28 | Fusion: repo structure, Council, velocity, + règles existantes |
| 1.x | 2026-01-xx | Version originale avec Gateway modes et Common Tasks |
