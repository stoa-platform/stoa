# 📊 STOA Platform - Capacity Planning Q1-Q3 2026

**Date:** 03/01/2026
**Version:** 2.0 (post Phase 3 completion)
**Target:** Release v1.0 - 31 Juillet 2026

---

## 📈 Synthèse

| Trimestre | Jalon | Jours estimés | Jours restants | Progression |
|-----------|-------|---------------|----------------|-------------|
| **Q1** | Fondations (Logos) | 8j | **6.5j** | 19% ✅ |
| **Q2** | Stabilité (Apatheia) | 10j | 10j | 0% |
| **Q3** | Release v1.0 | 9j | 9j | 0% |
| **TOTAL** | | **27j** | **25.5j** | **6%** |

---

## 🔵 Q1 2026 - Fondations (Logos)
**Deadline:** 31 Mars 2026 | **Linear:** CAB-171

### Issues par Phase

| Phase | Scope | Est. | Issues | Statut |
|-------|-------|------|--------|--------|
| **3** | Vault + Secrets | 1.5j | CAB-6 (epic) + 5 sub | ✅ **DONE** |
| **12** | MCP Gateway | 2j | CAB-119 (epic) + 5 sub | 🟡 1/6 (CAB-120 ✅) |
| **2.6** | Cilium Foundation | 1.25j | CAB-126 (epic) + 6 sub | ⬜ Backlog |
| **14** | GTM Strategy (01-03) | 1j | CAB-201, 202, 203 | ⬜ Backlog |
| **4** | OpenSearch + Monitoring | 1.25j | CAB-2 (epic) + 4 sub | ⬜ Backlog |
| **5** | Multi-env STAGING | 1j | CAB-3 (epic) + 3 sub | ⬜ Backlog |

### Détail Issues Q1

#### Phase 3 - Vault + Alias ✅ DONE
- [x] CAB-6: [Phase 3] Vault + Alias - Finalisation (Epic)
- [x] CAB-133: APIM-301: Déployer Vault sur EKS
- [x] CAB-134: APIM-302: Configurer Auth Kubernetes Vault
- [x] CAB-135: APIM-303: Structure secrets par tenant
- [x] CAB-136: APIM-304: Intégration Control Plane → Vault
- [x] CAB-137: APIM-305: Rotation automatique credentials

#### Phase 12 - MCP Gateway (🟡 En cours)
- [ ] CAB-119: [Phase 12] STOA Gateway + Copilot (Epic)
- [x] CAB-120: MCP-1201: Gateway Core + Auth Keycloak ✅
- [ ] CAB-199: MCP-1201b: Gateway Tests & Tools (Todo)
- [ ] CAB-121: MCP-1202: Tool Registry CRDs Kubernetes
- [ ] CAB-122: MCP-1203: OPA Policy Engine Integration
- [ ] CAB-123: MCP-1204: Metering Pipeline (Kafka + ksqlDB)
- [ ] CAB-124: MCP-1205: Portal Integration - Tool Catalog

#### Phase 2.6 - Cilium Foundation
- [ ] CAB-126: [Phase 2.6] Cilium Network Foundation (Epic)
- [ ] CAB-127: APIM-261: Installer Cilium sur EKS
- [ ] CAB-128: APIM-262: Gateway API CRDs + GatewayClass
- [ ] CAB-129: APIM-263: Migrer Nginx Ingress → Gateway API
- [ ] CAB-130: APIM-264: CiliumNetworkPolicy - Default deny
- [ ] CAB-131: APIM-265: Hubble - Observabilité réseau
- [ ] CAB-132: APIM-266: Documentation migration Cilium

#### Phase 14 - GTM Q1 (Strategy)
- [ ] CAB-201: GTM-01: Stratégie Open Core documentée
- [ ] CAB-202: GTM-02: Licensing choice (Apache 2.0 vs dual)
- [ ] CAB-203: GTM-03: Repository structure (mono vs multi-repo)

#### Phase 4 - OpenSearch + Monitoring
- [ ] CAB-2: [Phase 4] OpenSearch + Monitoring (Epic)
- [ ] CAB-9: APIM-401: Déployer Amazon OpenSearch sur EKS
- [ ] CAB-10: APIM-402: Configurer FluentBit pour log shipping
- [ ] CAB-11: APIM-403: Déployer Prometheus + Grafana
- [ ] CAB-12: APIM-404: Créer dashboards OpenSearch

#### Phase 5 - Multi-environnement
- [ ] CAB-3: [Phase 5] Multi-environnement (Epic)
- [ ] CAB-13: APIM-501: Créer environnement STAGING
- [ ] CAB-14: APIM-502: Playbook promote-environment.yaml
- [ ] CAB-15: APIM-503: AWX Job Template Promote API

### Métriques Q1
- **Total issues:** 31
- **Done:** 7 (22%)
- **Remaining:** 24

---

## 🟡 Q2 2026 - Stabilité (Apatheia)
**Deadline:** 30 Juin 2026 | **Linear:** CAB-172

### Issues par Phase

| Phase | Scope | Est. | Issues | Statut |
|-------|-------|------|--------|--------|
| **8** | Portal Self-Service | 2j | CAB-5 (epic) + 6 sub | ⬜ Backlog |
| **9** | Ticketing ITSM | 2j | CAB-4 (epic) + 8 sub | ⬜ Backlog |
| **7** | Security Jobs | 1.25j | CAB-8 (epic) + 5 sub | ⬜ Backlog |
| **9.5** | Production Readiness | 2.5j | CAB-103 (epic) + 7 sub | 🟡 1/8 (CAB-107 ✅) |
| **6** | Demo Tenant | 0.75j | CAB-7 (epic) + 4 sub | ⬜ Backlog |
| **14** | GTM Docs + Site (04-07) | 1.5j | CAB-204, 205, 206, 207, 208 | ⬜ Backlog |

### Détail Issues Q2

#### Phase 8 - Portal Self-Service
- [ ] CAB-5: [Phase 8] Portal Self-Service (Epic)
- [ ] CAB-26: APIM-801: Setup projet Developer Portal
- [ ] CAB-145: APIM-802: Catalogue APIs navigable
- [ ] CAB-146: APIM-803: Gestion applications et souscriptions
- [ ] CAB-147: APIM-804: Dashboard consommation développeur
- [ ] CAB-148: APIM-805: Onboarding guidé nouveaux développeurs
- [ ] CAB-188: [Portal] Setup i18n infrastructure

#### Phase 9 - Ticketing ITSM
- [ ] CAB-4: [Phase 9] Ticketing ITSM (Epic)
- [ ] CAB-16: APIM-901: Modèle PromotionRequest + Service Git
- [ ] CAB-17: APIM-902: Endpoints API /v1/requests/prod
- [ ] CAB-18: APIM-903: Workflow Approve/Reject
- [ ] CAB-19: APIM-904: Webhook callback AWX
- [ ] CAB-20: APIM-905: UI - Page liste demandes
- [ ] CAB-21: APIM-906: UI - Formulaire nouvelle demande
- [ ] CAB-22: APIM-907: UI - Page détail + Approve/Reject
- [ ] CAB-23: APIM-908: Events Kafka + Notifications

#### Phase 7 - Security Jobs
- [ ] CAB-8: [Phase 7] Security Jobs (Epic)
- [ ] CAB-25: APIM-701: Image Docker apim-security-jobs
- [ ] CAB-141: APIM-702: Scan vulnérabilités images (Trivy)
- [ ] CAB-142: APIM-703: Détection secrets dans code (Gitleaks)
- [ ] CAB-143: APIM-704: Monitoring expiration certificats TLS
- [ ] CAB-144: APIM-705: Compliance checks CIS Benchmark

#### Phase 9.5 - Production Readiness
- [ ] CAB-103: Phase 9.5: Production Readiness (Epic)
- [ ] CAB-104: APIM-9501: Backup/Restore AWX
- [ ] CAB-105: APIM-9502: Backup/Restore Vault
- [ ] CAB-106: APIM-9503: Load Test Pipeline (K6/Gatling)
- [x] CAB-107: APIM-9504: Runbooks Opérationnels ✅
- [ ] CAB-108: APIM-9505: Security Audit (OWASP)
- [ ] CAB-109: APIM-9506: Chaos Testing
- [ ] CAB-110: APIM-9507: SLO/SLA Definition
- [ ] CAB-187: [Docs] Internationalization - Switch to English

#### Phase 6 - Demo Tenant
- [ ] CAB-7: [Phase 6] Demo Tenant (Epic)
- [ ] CAB-24: APIM-601: Créer tenant demo avec users beta
- [ ] CAB-138: APIM-602: Déployer APIs demo
- [ ] CAB-139: APIM-603: Documenter scénarios de démo
- [ ] CAB-140: APIM-604: Reset automatique tenant demo

#### Phase 14 - GTM Q2 (Docs + Site)
- [ ] CAB-204: GTM-04: Documentation publique (Docusaurus)
- [ ] CAB-205: GTM-05: Landing page STOA
- [ ] CAB-206: GTM-06: Community channels (Discord, GitHub)
- [ ] CAB-207: GTM-07: Roadmap publique
- [ ] CAB-208: GTM-08: IBM Partnership positioning

### Métriques Q2
- **Total issues:** 40
- **Done:** 1 (2.5%)
- **Remaining:** 39

---

## 🚀 Q3 2026 - Release v1.0 (Oikeiosis + Ataraxia)
**Deadline:** 31 Juillet 2026 | **Linear:** CAB-173

### Issues par Phase

| Phase | Scope | Est. | Issues | Statut |
|-------|-------|------|--------|--------|
| **10** | Resource Lifecycle | 3j | CAB-27 (epic) + 10 sub | ⬜ Backlog |
| **4.5** | Jenkins Orchestration | 3j | CAB-92 (epic) + 10 sub | ⬜ Backlog |
| **14** | GTM Launch (08-10) | 1j | CAB-209, 210 | ⬜ Backlog |
| **11** | Resource Advanced (bonus) | 2j | CAB-82 (epic) + 8 sub | ⬜ Backlog |

### Détail Issues Q3

#### Phase 10 - Resource Lifecycle Management
- [ ] CAB-27: [Phase 10] Resource Lifecycle Management (Epic)
- [ ] CAB-28: APIM-1001: Module Terraform common_tags
- [ ] CAB-29: APIM-1002: Lambda Resource Cleanup
- [ ] CAB-30: APIM-1003: EventBridge Schedule
- [ ] CAB-31: APIM-1004: Notifications Owner Expiration
- [ ] CAB-32: APIM-1005: OPA Gatekeeper Policies
- [ ] CAB-33: APIM-1006: GitHub Actions Tag Governance
- [ ] CAB-34: APIM-1007: Kafka Events Resource Lifecycle
- [ ] CAB-35: APIM-1008: Dashboard Grafana Resource Lifecycle
- [ ] CAB-36: APIM-1009: n8n Workflow Multi-Cloud (optionnel)
- [ ] CAB-37: APIM-1010: Documentation Tagging Policy

#### Phase 4.5 - Jenkins Orchestration Layer
- [ ] CAB-92: [Phase 4.5] Jenkins Orchestration Layer (Epic)
- [ ] CAB-93: [Jenkins] Déploiement Jenkins sur EKS avec JCasC
- [ ] CAB-94: [Jenkins] Intégration Keycloak OIDC pour SSO
- [ ] CAB-95: [Jenkins] Service Kafka Consumer → Jenkins Job Trigger
- [ ] CAB-96: [Jenkins] Pipeline Deploy API avec Approval Gates
- [ ] CAB-97: [Jenkins] Pipeline Rollback API
- [ ] CAB-98: [Jenkins] Shared Library fonctions réutilisables
- [ ] CAB-99: [Jenkins] Intégration AWX Job Trigger
- [ ] CAB-100: [Jenkins] Métriques Prometheus et Dashboard Grafana
- [ ] CAB-101: [Jenkins] Pipeline Sync Gateway Configuration
- [ ] CAB-102: [Jenkins] Blue Ocean UI et organisation jobs

#### Phase 14 - GTM Q3 (Launch)
- [ ] CAB-209: GTM-09: Pricing tiers definition
- [ ] CAB-210: GTM-10: Beta program structure

#### Phase 11 - Resource Lifecycle Advanced (Bonus)
- [ ] CAB-82: [Phase 11] Resource Lifecycle Advanced (Epic)
- [ ] CAB-83: [Terraform] Quotas par projet/tenant
- [ ] CAB-84: [Config] Whitelist ressources never-delete
- [ ] CAB-85: [Lambda] Destruction ordonnée avec dépendances
- [ ] CAB-86: [API] Endpoint self-service TTL Extension
- [ ] CAB-87: [Lambda] Boutons Snooze dans emails
- [ ] CAB-88: [Lambda] Calculateur coût évité
- [ ] CAB-89: [Grafana] Dashboard Cost Savings
- [ ] CAB-90: [n8n] Workflow complet avec Notion
- [ ] CAB-91: [Lambda] Cron horaire pré-alertes

### Métriques Q3
- **Total issues:** 33
- **Done:** 0 (0%)
- **Remaining:** 33

---

## 📊 Vue d'ensemble des Issues

| Statut | Count | % |
|--------|-------|---|
| ✅ Done | 11 | 11% |
| 🟡 Todo | 1 | 1% |
| ⬜ Backlog | 81 | 88% |
| **TOTAL** | **93** | 100% |

### Issues Done
1. CAB-6: [Phase 3] Vault + Alias - Finalisation ✅
2. CAB-133: APIM-301: Déployer Vault sur EKS ✅
3. CAB-134: APIM-302: Configurer Auth Kubernetes Vault ✅
4. CAB-135: APIM-303: Structure secrets par tenant ✅
5. CAB-136: APIM-304: Intégration Control Plane → Vault ✅
6. CAB-137: APIM-305: Rotation automatique credentials ✅
7. CAB-120: MCP-1201: Gateway Core + Auth Keycloak ✅
8. CAB-196: [Infra] Rebranding APIM → STOA ✅
9. CAB-197: [Infra] Migration DNS/TLS vers *.stoa.cab-i.com ✅
10. CAB-198: [Infra] Architecture configuration centralisée BASE_DOMAIN ✅
11. CAB-107: APIM-9504: Runbooks Opérationnels ✅

---

## 🎯 Prochaines actions prioritaires

### Immédiat (cette semaine)
1. **CAB-199** - MCP Gateway Tests & Tools (Todo → In Progress)
2. Finaliser Phase 12 pour atteindre 50% Q1

### Court terme (Janvier 2026)
1. Phase 2.6 - Cilium Foundation (network modernization)
2. Phase 14 GTM - Open Core Strategy docs

### Moyen terme (Février-Mars 2026)
1. Phase 4 - OpenSearch + Monitoring
2. Phase 5 - Multi-env STAGING

---

## 📅 Disponibilité estimée

**Hypothèse:** ~8h/semaine disponibles pour STOA (hors BDF)

| Mois | Semaines | Heures dispo | Jours equiv. |
|------|----------|--------------|--------------|
| Janvier | 4 | 32h | 4j |
| Février | 4 | 32h | 4j |
| Mars | 4 | 32h | 4j |
| **Q1 Total** | 12 | 96h | **12j** |
| Avril | 4 | 32h | 4j |
| Mai | 4 | 32h | 4j |
| Juin | 4 | 32h | 4j |
| **Q2 Total** | 12 | 96h | **12j** |
| Juillet | 4 | 32h | 4j |
| **Q3 (partiel)** | 4 | 32h | **4j** |

**Capacité totale Q1-Q3:** ~28j → **Estimation restante: 25.5j** ✅ Réalisable

---

*Généré le 03/01/2026 - Basé sur 93 issues Linear*
