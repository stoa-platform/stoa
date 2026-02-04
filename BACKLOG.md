# STOA Platform — BACKLOG.md

> **Migré depuis Linear le 2026-02-04** dans le cadre du Mode Phase (CAB-1051)
>
> Ce fichier remplace le Backlog Linear. Les idées ici sont valides mais pas prioritaires pour le MVP.

---

## 🎯 Post-MVP Explicites

| ID | Titre | Notes |
|----|-------|-------|
| CAB-1054 | [MEGA] Portal & Console UX — Post-MVP | UX polish après démo |
| CAB-1055 | [MEGA] DX & Community — Post-MVP | Community features |
| CAB-1049 | [Plan] Roadmap Q2 Post-Démo — Gaps Concurrentiels | Planning stratégique |

---

## 🔮 Vision & Strategy

| ID | Titre | Notes |
|----|-------|-------|
| CAB-1046 | Enterprise MCP Federation — N Devs/Agents → 1 Master Account | Vision enterprise |
| CAB-1045 | STOA = MCP to Everything — Gap Analysis & North Star | Positionnement long terme |

---

## ⚡ MCP Gateway & Features Avancées

| ID | Titre | Notes |
|----|-------|-------|
| CAB-1053 | [MEGA] MCP Gateway & Platform Features | Features MCP avancées |
| CAB-1047 | STOA Skills System - Context injection hiérarchique | Skills pour agents IA |
| CAB-1037 | Automated Tenant Provisioning — "One API Call" Onboarding | Self-service tenants |
| CAB-1032 | Consumer Execution View UI — Error taxonomy dashboard | Dashboard erreurs |
| CAB-952 | UAC ConfigMap-based Architecture — OpenShift/Enterprise | Compatibilité OpenShift |
| CAB-962 | Intermediate Hop Detection — Network Path Analysis | Observabilité réseau |
| CAB-961 | Self-Diagnostic Engine — Auto Root Cause Analysis | RCA automatique |
| CAB-725 | MCP Developer Self-Service (Logs, Metrics, Models Discovery) | Self-service dev |
| CAB-822 | MCP Proxy Hardening — OAuth flows, Lazy discovery, Circuit Breaker | Hardening Phase 3 |

---

## 👥 Community

| ID | Titre | Notes |
|----|-------|-------|
| CAB-1027 | GitHub Templates — Issues & PR Templates | Templates contribution |
| CAB-386 | Good First Issues — 10 Starter Issues Template | Onboarding contributeurs |

---

## 🔧 Infra & DevOps

| ID | Titre | Notes |
|----|-------|-------|
| CAB-1026 | Évaluation Migration Scaleway Kapsule — Souveraineté & Coûts | Alternative cloud souverain |
| CAB-441 | Multi-Arch Docker Build — Mac ARM → AWS AMD64 | Build cross-platform |
| CAB-980 | Helm: Auto-sync postgres-exporter secret | Secret management |
| CAB-977 | Multi-Staging Pattern OpenShift & Enterprise CI/CD | Pattern enterprise |
| CAB-1020 | [MEGA] Repo Consolidation — stoa/ cleanup + stoa-charts | Réorg repos |

---

## 📊 Observability

| ID | Titre | Notes |
|----|-------|-------|
| CAB-357 | Monitoring Alerts Tuning | Fine-tuning alertes |
| CAB-934 | Evaluate Ansible-style UAC inheritance at 15+ tenants | Scalabilité config |

---

## 🖥️ Portal & UX

| ID | Titre | Notes |
|----|-------|-------|
| CAB-849 | Communautés Multi-Audience — Filtrage Public/Internal | Multi-audience portal |
| CAB-700 | RBAC Affinage complet UI — Widgets, Tenant Isolation, Grafana | RBAC fine-grained |
| CAB-789 | PERSONA: CPI Proxy Owner Dashboard | Dashboard persona spécifique |

---

## 🏗️ Architecture

| ID | Titre | Notes |
|----|-------|-------|
| CAB-850 | Runtime Data Governance — Control Plane vs Git | Data governance pattern |
| CAB-408 | Prospect Self-Onboarding — Zero-Touch Trial Experience | Onboarding prospects |

---

## 📋 Règles

1. **Pas de ticket Linear** pour ces items tant qu'ils ne sont pas priorisés
2. **Review mensuelle** : trier KEEP / KILL / DEFER
3. **Promotion** : Si un item devient critique → créer ticket Linear + supprimer d'ici

---

---

## 📦 Phase 3 — Todo Migrated (16 tickets)

### Demo Content
- [ ] **CAB-833** : Valider scénarios Ready Player One sur Portal UI
- [ ] **CAB-920** : Demo: La Citadelle — Enterprise Fonction Publique (RGS/SecNumCloud)
- [ ] **CAB-923** : Demo: Neo's Workshop — Personal AI Gateway (Token Optimization)
- [ ] **CAB-916** : Demo: Middle-Earth Banking — Enterprise Banque (NIS2/DORA)
- [ ] **CAB-915** : EPIC: Demo Content Library — 8 Univers Thématiques HLFH

### UX & Portal
- [ ] **CAB-1029** : Full Feature UX Audit — Apple-Style Minimalism Pass
- [ ] **CAB-971** : Portal Governance — Multi-Audience + RBAC Affinage

### MCP Gateway
- [ ] **CAB-1038** : Hot-Reload Tools — notifications/tools/list_changed via SSE

### Observability
- [ ] **CAB-892** : UAC-Driven Observability — Debug chirurgical sans tcpdump
- [ ] **CAB-801** : Hybrid Observability Dashboard — Cloud + On-Prem Unified

### Community & Docs
- [ ] **CAB-994** : Community Launch Preparation — Checklist Pré-Partage Réseau
- [ ] **CAB-731** : Docs as Code + RAG Chatbot — Eat Your Own Dog Food
- [ ] **CAB-1015** : Documentation Separation - Notion vs docs.gostoa.dev

### Demo & CI
- [ ] **CAB-453** : Living Demo Instance — Animated Scenarios per Sector
- [ ] **CAB-979** : CI Security Showcase — Gestion exemplaire code AI-generated

### Ops
- [ ] **CAB-853** : PostgreSQL Backup — Retention Policy + Test Restore

---

*Dernière mise à jour : 2026-02-04*
