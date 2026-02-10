# STOA Demo Scope — "Full Stack, AI Factory Speed"

> Date: 10 fevrier 2026 | Revise: feedback fondateur
> Demo client: **24 fevrier 2026** ("ESB is Dead")
> Post-demo polish: 24 fev → 10 mars (2 semaines)
> Velocite AI Factory: **225 pts / 2 jours** — pas de raison de se priver

---

## Vision — AI Agent DNA

**STOA n'est pas un API gateway qui fait du MCP. STOA est le premier gateway ne dans l'ere des AI Agents.**

Trois dimensions ou l'IA Agent est dans l'ADN:

| Dimension | Ce que ca veut dire | Preuve |
|-----------|-------------------|--------|
| **Built BY AI Agents** | L'AI Factory (Claude Opus) construit la plateforme | 225 pts / 2 jours, 22 PRs, zero regression |
| **Built FOR AI Agents** | MCP Gateway, tool discovery, legacy-to-MCP bridge | Protocole MCP natif, pas ajoute apres coup |
| **Built WITH AI Agents** | AI-assisted ops, self-healing, autonomous monitoring | AI Factory rules, auto-state management |

Les concurrents (Kong, Apigee, MuleSoft) ajouteront "MCP support" comme un plugin en 2027.
STOA l'a dans l'architecture depuis le jour 1. C'est la difference entre "AI-washed" et "AI-native".

**On ne coupe pas. On livre vite.** L'AI Factory produit a ~112 pts/jour.
Le client attend une plateforme complete, pas un POC.

**Decision strategique**: capitaliser sur Rust des maintenant. Pas de retour au Python Gateway.
L'AI Factory permet de tenir les deux fronts (Rust + full stack) simultanement.

---

## Demo 24 fev — "ESB is Dead, AI Agents Are Here"

**Narrative**: On ne montre pas un gateway. On montre comment les AI Agents remplacent l'ESB.
Le client ne voit pas des features, il voit un changement de paradigme.

| # | Experience | Message pour le client | Composants |
|---|-----------|----------------------|-----------|
| **1** | **Admin Console** | "Votre equipe plateforme gere tout ici" | Console + API + Keycloak |
| **2** | **Developer Portal** | "Vos developpeurs et partenaires se servent eux-memes" | Portal + API + Keycloak |
| **3** | **Gateway Rust** | "Zero latence, zero compromis — built in Rust" | Rust Gateway (basic mode) |
| **4** | **Observabilite** | "Visibilite totale, temps reel, error snapshots" | Grafana + Prometheus + Loki + OpenSearch |
| **5** | **Federation SSO** | "Un login, tous vos tenants — souverainete europeenne" | Keycloak federe |
| **6** | **MCP Bridge** | "Vos APIs legacy deviennent des tools pour Claude/GPT" | MCP Gateway |
| **7** | **AI Factory** | "Cette plateforme a ete construite en 2 jours par des AI Agents" | Slide + chiffres |

**Acte 7 est la bombe**: montrer que STOA a ete construit par l'AI Factory (225 pts, 22 PRs, zero regression).
Ca prouve que l'AI Agent n'est pas du marketing — c'est le mode operatoire.

---

## IN — Composants Demo

### Core Platform

| Composant | Path | Status actuel | Objectif demo | Effort estime |
|-----------|------|---------------|---------------|---------------|
| **Control Plane API** | `control-plane-api/` | Production (53%, 291 tests) | Stable, zero regression | Faible |
| **Admin Console** | `control-plane-ui/` | Production (manual QA) | Full flow admin fonctionnel | Faible |
| **Developer Portal** | `portal/` | Production (manual QA) | Full flow consumer fonctionnel | Faible |
| **Shared UI** | `shared/` | Production | Dark mode, theme coherent | Nul |
| **Keycloak** | `keycloak/` | Production | + Federation config | Moyen |
| **PostgreSQL** | docker-compose | Production | Inchange | Nul |

### Rust Gateway (basic mode)

| Feature | Status actuel | Objectif demo | Priorite |
|---------|---------------|---------------|----------|
| JWT validation | Beta (fonctionnel) | Stable | P0 |
| Request proxy | Beta | Stable | P0 |
| Health endpoints | Beta | Stable | P0 |
| Circuit breaker | Beta | Basic (on/off) | P1 |
| mTLS | Beta (870 LOC) | Basic (header extraction) | P2 |
| Rate limiting | Beta | Basic (per-consumer) | P1 |
| Admin API | Beta | `/health`, `/admin/stats` | P1 |

**Strategie**: le Rust Gateway tourne en mode basic. Pas de features avancees (UAC, shadow, sidecar).
Le Python MCP Gateway reste disponible pour le bridge legacy-to-MCP si besoin en demo.
Post-demo: migration acceleree vers Rust pour tout.

### Observabilite (client attend)

| Composant | Status actuel | Objectif demo |
|-----------|---------------|---------------|
| **Prometheus** | GA (docker-compose) | Metriques API + Gateway |
| **Grafana** | GA (dashboards STOA) | Dashboard overview + OIDC via Keycloak |
| **Loki + Promtail** | GA | Logs centralises tous composants |
| **OpenSearch** | Beta (TLS + OIDC) | Error snapshots indexees, dashboard STOA Logs |
| **OpenSearch Dashboards** | Beta | UI recherche errors, branding STOA |
| **AlertManager** | GA | Alerting basique (optionnel si temps manque) |

### Keycloak Federation

| Feature | Status | Objectif demo |
|---------|--------|---------------|
| Realm STOA | GA | Inchange |
| OIDC clients (Console, Portal, Grafana) | GA | Fonctionnels |
| Federation identity provider | Alpha/Config | Login federe cross-realm |
| Multi-tenant isolation | GA | Tenant isolation via realm roles |

---

## OUT — Vrai report

Ces features sont reportees car elles ne servent pas la demo client et/ou necessitent un effort disproportionne.

| Feature | Raison | Quand |
|---------|--------|-------|
| **UAC** (Universal API Contract) | Concept non prouve, pas attendu par client | Post-PMF |
| **Kafka metering** | Ajoute un broker Kafka, pas visible en demo | Post-demo (+2 sem) |
| **Shadow mode** | Complexe, necessite traffic reel | v2 |
| **Sidecar mode** | 1 mode suffit pour demo | Post-demo |
| **Proxy mode** | Design only | v2 |
| **CLI** (`stoactl`) | Console couvre les actions admin | v2 |
| **Helm chart production** | Docker-compose pour demo, Helm pour deploy client | Post-demo |
| **webMethods adapter** | Specifique, pas dans le scope demo | Sur demande client |
| **Kong adapter** | Idem | Sur demande |

---

## Quickstart — Architecture Demo

### Tous les services (Option B + Observabilite)

```
docker-compose.yml (demo):
  postgres              — Database
  keycloak              — Auth + Federation
  db-migrate            — One-shot migrations
  control-plane-api     — API backend
  control-plane-ui      — Admin Console
  portal                — Developer Portal
  stoa-gateway          — Rust Gateway (basic mode)
  nginx                 — Reverse proxy
  prometheus            — Metriques
  grafana               — Dashboards
  loki                  — Log aggregation
  promtail              — Log shipping
  opensearch            — Search + error snapshots
  opensearch-dashboards — STOA Logs UI
  opensearch-init       — One-shot index setup
```

**15 services** (dont 2 one-shot). C'est la plateforme complete.

Pour la communaute / public launch, on fournit aussi un profil leger:

```bash
# Demo complete (client)
docker compose up

# Quickstart leger (communaute, devs)
docker compose --profile light up
# = postgres + keycloak + api + portal + gateway + nginx (6 services)
```

---

## Timeline 10-24 fev

### Semaine 1 (10-16 fev) — Fondations

| Jour | Focus | Pts estimes |
|------|-------|-------------|
| Mar 11 | Rust GW stabilisation (basic mode: JWT, proxy, health) | 30 |
| Mer 12 | Keycloak federation config + test cross-tenant | 20 |
| Jeu 13 | OpenSearch polish (error snapshots, STOA branding) | 15 |
| Ven 14 | Grafana dashboards (overview, per-tenant, gateway) | 15 |
| Sam 15 | Integration test: full flow admin → consumer → gateway → metrics | 20 |

### Semaine 2 (17-23 fev) — Polish + Demo prep

| Jour | Focus | Pts estimes |
|------|-------|-------------|
| Lun 17 | Docker-compose demo final (tous services, seed data) | 20 |
| Mar 18 | Demo script dry-run #1 + fix frictions | 15 |
| Mer 19 | README public (anglais, screenshots) + demo video draft | 15 |
| Jeu 20 | Bug fixes, dark mode polish, UX consistency | 15 |
| Ven 21 | Demo script dry-run #2 (chrono < 15 min) | 10 |
| Sam-Dim 22-23 | Buffer / derniers ajustements | 10 |

**Total estime: ~185 pts** (confortable avec velocite de 112 pts/jour)

### 24 fev — Demo Day

```
Demo "ESB is Dead, AI Agents Are Here" (20 min):
1. Console: creer tenant "acme" + publier API           (3 min)
2. Portal: s'inscrire, subscribe, obtenir token          (3 min)
3. Rust Gateway: appel API, JWT valide, zero latence     (2 min)
4. Grafana: dashboards live, metriques temps reel        (2 min)
5. OpenSearch: error snapshot, recherche logs STOA       (2 min)
6. Keycloak: federation login cross-tenant               (2 min)
7. MCP Bridge: legacy API → MCP tool pour Claude/GPT     (3 min)
8. AI Factory: "10 personnes = le travail de 300 devs"   (2 min)
   → 225 pts, 22 PRs, 2 jours, construit par AI Agents
```

### Post-demo (24 fev → 10 mars) — 2 semaines polish

| Focus | Objectif |
|-------|----------|
| Rust Gateway migration acceleree | Remplacer Python MCP GW par Rust endpoints |
| Kafka metering | Ajouter broker + producer dans gateway |
| E2E tests full flow | Playwright scenarios complets |
| README + tutorial + HN post | Community launch |
| Pricing page | gostoa.dev (CAB-1066) |

---

## Impact repos

| Repo | Action |
|------|--------|
| **stoa** | Composant principal. Tous composants actifs sauf CLI |
| **stoa-docs** | Tutorial 5-min, quickstart guide (post-demo) |
| **stoa-web** | Landing + pricing (CAB-1066, parallele) |
| **stoa-infra** | Prive, inchange |
| **stoactl** | Reporte v2 |

---

## Binary DoD — S1 (revise)

| Check | Critere | Status |
|-------|---------|--------|
| Document scope existe | Ce fichier | ✅ |
| Composants IN listes avec objectif demo | Tableau complet | ✅ |
| Features OUT avec raisons | Chaque item justifie | ✅ |
| Timeline jour par jour | 10-24 fev planifie | ✅ |
| Demo script esquisse | 7 actes, 15-20 min | ✅ |
| Strategie Rust = primaire | Decision documentee | ✅ |
| Approuve par fondateur | Ci-dessous | ✅ 2026-02-10 |

### Approbation

- [x] **Fondateur**: J'approuve ce scope (date: 2026-02-10)
- [x] **Decision**: Option B — Console + Observabilite + Federation dans le quickstart
- [x] **Decision**: Rust Gateway = mode basic pour demo, migration acceleree post-demo
- [x] **Decision**: Pas de retour au Python Gateway

---

*Document revise le 2026-02-10 par Claude Opus 4.6 — AI Factory, STOA Platform*
*Velocite de reference: 225 pts en 2 jours (Cycle 7)*
