# Linear Import - APIM Platform v2

## Configuration Linear

### Labels à créer

#### Par Phase
- `phase:4` - AWX Integration
- `phase:5` - Vault Integration
- `phase:6` - Multi-Environment
- `phase:7` - Security Jobs
- `phase:8` - Developer Portal
- `phase:9` - Ticketing System

#### Par Type
- `type:feature` - Nouvelle fonctionnalité
- `type:integration` - Intégration système
- `type:security` - Sécurité
- `type:infra` - Infrastructure
- `type:ui` - Interface utilisateur
- `type:api` - Backend API
- `type:docs` - Documentation

#### Par Composant
- `component:awx` - AWX/Ansible
- `component:vault` - HashiCorp Vault
- `component:kafka` - Kafka/Redpanda
- `component:keycloak` - Keycloak SSO
- `component:gateway` - Kong Gateway
- `component:gitlab` - GitLab
- `component:ui` - Control Plane UI
- `component:api` - Control Plane API

#### Par Priorité
- `priority:p0` - Critique (bloquant)
- `priority:p1` - Haute
- `priority:p2` - Moyenne
- `priority:p3` - Basse

---

## Milestones

| Milestone | Description | Phases |
|-----------|-------------|--------|
| **M1: Production-Ready** | Plateforme prête pour production | 4, 5, 9 |
| **M2: Self-Service** | Portail développeur autonome | 6, 8 |
| **M3: Full Automation** | Automatisation complète | 7 |

---

## Cycles Suggérés

| Cycle | Durée | Phases | Focus |
|-------|-------|--------|-------|
| Sprint 1 | 2 semaines | Phase 4 (AWX) | Automation Foundation |
| Sprint 2 | 2 semaines | Phase 5 (Vault) | Secrets Management |
| Sprint 3 | 1 semaine | Phase 9 (Ticketing) | Production Workflow |
| Sprint 4 | 2 semaines | Phase 6 (Multi-Env) | Environment Management |
| Sprint 5 | 1 semaine | Phase 7 (Security) | Security Automation |
| Sprint 6-8 | 3 semaines | Phase 8 (Portal) | Developer Experience |

---

## Statut Actuel du Projet

### Phases Complétées ✅

| Phase | Nom | Status |
|-------|-----|--------|
| Phase 1 | Infrastructure Foundation | ✅ Completed |
| Phase 2 | Event-Driven Core | ✅ Completed |
| Phase 2.5 | OpenAPI Compatibility | ✅ Completed |
| Phase 3 | GitOps Foundation | ✅ Completed |

### Phases À Faire 📋

| Phase | Nom | Priorité | Estimation |
|-------|-----|----------|------------|
| Phase 4 | AWX Integration | P0 | 2 semaines |
| Phase 5 | Vault Integration | P0 | 2 semaines |
| Phase 9 | Ticketing System | P0 | 1 semaine |
| Phase 6 | Multi-Environment | P1 | 2 semaines |
| Phase 7 | Security Batch Jobs | P1 | 1.5 semaines |
| Phase 8 | Developer Portal | P2 | 3 semaines |

---

## Issues à Créer

### Phase 4 - AWX Integration (P0)

#### APIM-401: Configuration AWX et inventaires dynamiques
```
Title: [AWX] Configuration AWX et inventaires dynamiques
Priority: P0 - Urgent
Labels: phase:4, type:infra, component:awx, priority:p0
Milestone: M1: Production-Ready
Estimate: 3 days

Description:
Configurer AWX avec inventaires dynamiques pour les environnements APIM.

Acceptance Criteria:
- [ ] AWX installé et configuré sur le cluster
- [ ] Inventaires dynamiques par environnement (dev, staging, prod)
- [ ] Credentials GitLab configurés
- [ ] Credentials Vault configurés
- [ ] Credentials Kong Gateway configurés
- [ ] Health check AWX opérationnel
```

#### APIM-402: Playbooks de déploiement API
```
Title: [AWX] Playbooks de déploiement API (create/update/delete)
Priority: P0 - Urgent
Labels: phase:4, type:integration, component:awx, priority:p0
Milestone: M1: Production-Ready
Estimate: 4 days

Description:
Développer les playbooks Ansible pour le cycle de vie complet des APIs.

Acceptance Criteria:
- [ ] Playbook deploy-api.yaml fonctionnel
- [ ] Playbook update-api.yaml fonctionnel
- [ ] Playbook delete-api.yaml fonctionnel
- [ ] Playbook promote-api.yaml fonctionnel
- [ ] Gestion des rollbacks
- [ ] Tests unitaires des playbooks
- [ ] Documentation des variables
```

#### APIM-403: Consumer Kafka pour AWX
```
Title: [AWX] Consumer Kafka → AWX Job Trigger
Priority: P0 - Urgent
Labels: phase:4, type:integration, component:kafka, component:awx, priority:p0
Milestone: M1: Production-Ready
Estimate: 3 days

Description:
Développer le consumer Kafka qui déclenche les jobs AWX.

Acceptance Criteria:
- [ ] Consumer écoute topic `api.lifecycle.events`
- [ ] Mapping event_type → job_template
- [ ] Callback URL pour status updates
- [ ] Retry logic avec exponential backoff
- [ ] Dead letter queue pour événements en échec
- [ ] Métriques Prometheus exposées
```

#### APIM-404: Callback AWX vers Control Plane
```
Title: [AWX] Webhook callback AWX → Control Plane
Priority: High
Labels: phase:4, type:api, component:awx, priority:p1
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Implémenter le endpoint de callback pour recevoir les résultats des jobs AWX.

Acceptance Criteria:
- [ ] Endpoint POST /api/v1/awx/callback
- [ ] Validation signature HMAC
- [ ] Mise à jour statut déploiement en DB
- [ ] Émission événement Kafka `deployment.completed`
- [ ] Notification UI en temps réel (WebSocket)
```

#### APIM-405: UI Monitoring déploiements AWX
```
Title: [UI] Dashboard monitoring déploiements AWX
Priority: Medium
Labels: phase:4, type:ui, component:ui, priority:p1
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Développer l'interface de monitoring des déploiements dans le Control Plane UI.

Acceptance Criteria:
- [ ] Liste des déploiements en cours
- [ ] Statut temps réel (pending/running/success/failed)
- [ ] Logs de déploiement consultables
- [ ] Bouton retry pour déploiements échoués
- [ ] Filtres par API, environnement, statut
```

---

### Phase 5 - Vault Integration (P0)

#### APIM-501: Configuration Vault avec auth Kubernetes
```
Title: [Vault] Configuration Vault avec auth Kubernetes
Priority: P0 - Urgent
Labels: phase:5, type:infra, component:vault, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Configurer HashiCorp Vault avec authentification Kubernetes.

Acceptance Criteria:
- [ ] Vault déployé en HA mode
- [ ] Auth method Kubernetes configurée
- [ ] Policies par tenant créées
- [ ] Secret engine KV v2 activé
- [ ] Audit logging activé
- [ ] Unsealing automatique configuré
```

#### APIM-502: Structure secrets par tenant
```
Title: [Vault] Structure de secrets multi-tenant
Priority: P0 - Urgent
Labels: phase:5, type:security, component:vault, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Définir et implémenter la structure de secrets par tenant.

Acceptance Criteria:
- [ ] Path structure: secret/apim/{tenant}/{env}/{api}
- [ ] Policies RBAC par tenant
- [ ] Isolation complète entre tenants
- [ ] Rotation policies définies
- [ ] Templates secrets créés
```

#### APIM-503: API Secrets Management
```
Title: [API] Endpoints gestion secrets
Priority: P0 - Urgent
Labels: phase:5, type:api, component:vault, component:api, priority:p0
Milestone: M1: Production-Ready
Estimate: 3 days

Description:
Développer les endpoints de gestion des secrets dans le Control Plane API.

Acceptance Criteria:
- [ ] POST /api/v1/secrets - Créer secret
- [ ] GET /api/v1/secrets/{id} - Lire secret (masqué)
- [ ] PUT /api/v1/secrets/{id} - Mettre à jour
- [ ] DELETE /api/v1/secrets/{id} - Supprimer
- [ ] POST /api/v1/secrets/{id}/rotate - Rotation manuelle
- [ ] Audit trail complet
```

#### APIM-504: Injection secrets dans playbooks AWX
```
Title: [AWX] Injection secrets Vault dans playbooks
Priority: P0 - Urgent
Labels: phase:5, type:integration, component:vault, component:awx, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Intégrer la récupération des secrets Vault dans les playbooks AWX.

Acceptance Criteria:
- [ ] Module ansible-vault configuré
- [ ] Lookup plugin Vault fonctionnel
- [ ] Secrets injectés au runtime (jamais en logs)
- [ ] Fallback sur defaults si secret absent
- [ ] Rotation transparente supportée
```

#### APIM-505: UI Gestion Secrets
```
Title: [UI] Interface gestion secrets par API
Priority: High
Labels: phase:5, type:ui, component:ui, component:vault, priority:p1
Milestone: M1: Production-Ready
Estimate: 3 days

Description:
Développer l'interface de gestion des secrets dans le Control Plane UI.

Acceptance Criteria:
- [ ] Liste secrets par API (valeurs masquées)
- [ ] Formulaire création secret
- [ ] Bouton rotation avec confirmation
- [ ] Historique des rotations
- [ ] RBAC appliqué (tenant-admin+ seulement)
```

---

### Phase 9 - Ticketing System (P0)

#### APIM-901: Modèle données tickets production
```
Title: [API] Modèle de données tickets production
Priority: P0 - Urgent
Labels: phase:9, type:api, priority:p0
Milestone: M1: Production-Ready
Estimate: 1 day

Description:
Définir le modèle de données pour les tickets de production.

Acceptance Criteria:
- [ ] Table `production_requests` créée
- [ ] Table `request_approvals` créée
- [ ] Statuts: DRAFT, PENDING, APPROVED, REJECTED, DEPLOYED
- [ ] Types: DEPLOY, PROMOTE, ROLLBACK, DELETE
- [ ] Relation avec APIs et environnements
- [ ] Audit fields (created_at, updated_at, created_by)
```

#### APIM-902: API CRUD Tickets
```
Title: [API] Endpoints CRUD tickets production
Priority: P0 - Urgent
Labels: phase:9, type:api, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Développer les endpoints de gestion des tickets.

Acceptance Criteria:
- [ ] POST /api/v1/tickets - Créer ticket
- [ ] GET /api/v1/tickets - Liste avec filtres
- [ ] GET /api/v1/tickets/{id} - Détail ticket
- [ ] PUT /api/v1/tickets/{id} - Modifier (si DRAFT)
- [ ] POST /api/v1/tickets/{id}/submit - Soumettre
- [ ] POST /api/v1/tickets/{id}/cancel - Annuler
```

#### APIM-903: Workflow d'approbation anti-self-approval
```
Title: [API] Workflow approbation avec anti-self-approval
Priority: P0 - Urgent
Labels: phase:9, type:security, type:api, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Implémenter le workflow d'approbation avec règle anti-self-approval.

Acceptance Criteria:
- [ ] POST /api/v1/tickets/{id}/approve - Approuver
- [ ] POST /api/v1/tickets/{id}/reject - Rejeter avec raison
- [ ] Règle: requester != approver (OBLIGATOIRE)
- [ ] Vérification rôle cpi-admin ou tenant-admin
- [ ] Notification Kafka sur changement statut
- [ ] Email notification au requester
```

#### APIM-904: Intégration AWX pour exécution
```
Title: [AWX] Trigger déploiement après approbation ticket
Priority: P0 - Urgent
Labels: phase:9, type:integration, component:awx, priority:p0
Milestone: M1: Production-Ready
Estimate: 1 day

Description:
Déclencher automatiquement le déploiement AWX après approbation.

Acceptance Criteria:
- [ ] Event TICKET_APPROVED → AWX job trigger
- [ ] Lien ticket_id dans job extra_vars
- [ ] Callback met à jour statut ticket
- [ ] Rollback automatique si échec (optionnel)
```

#### APIM-905: UI Gestion Tickets
```
Title: [UI] Interface gestion tickets production
Priority: P0 - Urgent
Labels: phase:9, type:ui, component:ui, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Développer l'interface complète de gestion des tickets.

Acceptance Criteria:
- [ ] Liste tickets avec filtres (statut, type, tenant)
- [ ] Formulaire création ticket
- [ ] Vue détail avec timeline
- [ ] Boutons Approve/Reject (si autorisé)
- [ ] Badge count tickets pending dans sidebar
- [ ] Notifications temps réel
```

---

### Phase 6 - Multi-Environment (P1)

#### APIM-601: Modèle environnements par tenant
```
Title: [API] Modèle environnements multi-tenant
Priority: High
Labels: phase:6, type:api, priority:p1
Milestone: M2: Self-Service
Estimate: 2 days

Description:
Implémenter le modèle de données pour les environnements par tenant.

Acceptance Criteria:
- [ ] Table `environments` avec relation tenant
- [ ] Configuration Gateway par environnement
- [ ] Variables d'environnement stockées
- [ ] Ordre de promotion configurable
```

#### APIM-602: Promotion workflow
```
Title: [API] Workflow de promotion entre environnements
Priority: High
Labels: phase:6, type:api, priority:p1
Milestone: M2: Self-Service
Estimate: 3 days

Description:
Développer le workflow de promotion d'APIs entre environnements.

Acceptance Criteria:
- [ ] POST /api/v1/apis/{id}/promote
- [ ] Validation prérequis (tests, approbation)
- [ ] Diff de configuration avant promotion
- [ ] Rollback supporté
```

#### APIM-603: UI Gestion Environnements
```
Title: [UI] Interface gestion environnements
Priority: High
Labels: phase:6, type:ui, component:ui, priority:p1
Milestone: M2: Self-Service
Estimate: 2 days

Description:
Développer l'interface de gestion des environnements.

Acceptance Criteria:
- [ ] Liste environnements par tenant
- [ ] Configuration variables par env
- [ ] Visualisation pipeline promotion
- [ ] Bouton promote avec preview
```

---

### Phase 7 - Security Batch Jobs (P1)

#### APIM-701: Certificate Expiry Checker
```
Title: [Security] Job vérification expiration certificats
Priority: High
Labels: phase:7, type:security, priority:p1
Milestone: M3: Full Automation
Estimate: 2 days

Description:
Développer le job de vérification des certificats.

Acceptance Criteria:
- [ ] Scan tous certificats Gateway
- [ ] Alerte 30/14/7 jours avant expiration
- [ ] Rapport Kafka + Email
- [ ] Métriques Prometheus
```

#### APIM-702: Secret Rotation Job
```
Title: [Security] Job rotation automatique secrets
Priority: High
Labels: phase:7, type:security, component:vault, priority:p1
Milestone: M3: Full Automation
Estimate: 3 days

Description:
Développer le job de rotation automatique des secrets.

Acceptance Criteria:
- [ ] Rotation secrets > 90 jours
- [ ] Coordination avec Vault
- [ ] Zero-downtime rotation
- [ ] Audit trail complet
```

#### APIM-703: Usage Analytics Reporter
```
Title: [Security] Job rapport analytics usage APIs
Priority: Medium
Labels: phase:7, type:security, priority:p2
Milestone: M3: Full Automation
Estimate: 2 days

Description:
Développer le job de génération de rapports d'usage.

Acceptance Criteria:
- [ ] Collecte métriques Kong
- [ ] Agrégation par tenant/API
- [ ] Détection anomalies
- [ ] Export PDF/CSV
```

#### APIM-704: GitLab Security Scanner
```
Title: [Security] Job scan sécurité repos GitLab
Priority: High
Labels: phase:7, type:security, component:gitlab, priority:p1
Milestone: M3: Full Automation
Estimate: 2 days

Description:
Développer le job de scan de sécurité des repos.

Acceptance Criteria:
- [ ] Scan secrets exposés
- [ ] Scan dépendances vulnérables
- [ ] Intégration GitLab Security Dashboard
- [ ] Alertes critiques temps réel
```

---

### Phase 8 - Developer Portal (P2)

#### APIM-801: Setup Next.js Developer Portal
```
Title: [Portal] Setup projet Next.js Developer Portal
Priority: Medium
Labels: phase:8, type:infra, priority:p2
Milestone: M2: Self-Service
Estimate: 2 days

Description:
Initialiser le projet Developer Portal.

Acceptance Criteria:
- [ ] Next.js 14 avec App Router
- [ ] Tailwind CSS configuré
- [ ] Auth Keycloak intégrée
- [ ] API routes configurées
```

#### APIM-802: Catalogue APIs public
```
Title: [Portal] Catalogue APIs avec recherche
Priority: Medium
Labels: phase:8, type:ui, priority:p2
Milestone: M2: Self-Service
Estimate: 3 days

Description:
Développer le catalogue d'APIs publiques.

Acceptance Criteria:
- [ ] Liste APIs par catégorie
- [ ] Recherche full-text
- [ ] Filtres (version, status, tags)
- [ ] Page détail API
```

#### APIM-803: Documentation Swagger-UI
```
Title: [Portal] Intégration Swagger-UI
Priority: Medium
Labels: phase:8, type:ui, priority:p2
Milestone: M2: Self-Service
Estimate: 2 days

Description:
Intégrer Swagger-UI pour la documentation.

Acceptance Criteria:
- [ ] Swagger-UI embedded
- [ ] Thème personnalisé
- [ ] Try-It avec auth
- [ ] Code samples multi-langages
```

#### APIM-804: Console Try-It interactive
```
Title: [Portal] Console Try-It interactive
Priority: Medium
Labels: phase:8, type:ui, priority:p2
Milestone: M2: Self-Service
Estimate: 4 days

Description:
Développer la console Try-It pour tester les APIs.

Acceptance Criteria:
- [ ] Editeur requête avec syntax highlighting
- [ ] Gestion headers/params
- [ ] Historique requêtes
- [ ] Export cURL/code
```

#### APIM-805: Gestion API Keys self-service
```
Title: [Portal] Gestion API Keys self-service
Priority: Medium
Labels: phase:8, type:api, type:ui, priority:p2
Milestone: M2: Self-Service
Estimate: 3 days

Description:
Permettre aux développeurs de gérer leurs API keys.

Acceptance Criteria:
- [ ] Création API key
- [ ] Révocation
- [ ] Rate limits par key
- [ ] Usage statistics
```

---

## Import CSV (Optionnel)

Si Linear supporte l'import CSV, voici le format:

```csv
Title,Description,Priority,Labels,Milestone,Estimate
"[AWX] Configuration AWX et inventaires dynamiques","Configurer AWX avec inventaires dynamiques","Urgent","phase:4,type:infra,component:awx","M1: Production-Ready","3d"
"[AWX] Playbooks de déploiement API","Développer playbooks create/update/delete","Urgent","phase:4,type:integration,component:awx","M1: Production-Ready","4d"
...
```

---

## Dépendances entre Issues

```
APIM-403 (Kafka Consumer) ──depends on──► APIM-402 (Playbooks)
APIM-404 (Callback) ──depends on──► APIM-403 (Consumer)
APIM-405 (UI AWX) ──depends on──► APIM-404 (Callback)

APIM-504 (AWX Vault) ──depends on──► APIM-501 (Vault Config)
APIM-504 (AWX Vault) ──depends on──► APIM-402 (Playbooks)
APIM-505 (UI Secrets) ──depends on──► APIM-503 (API Secrets)

APIM-904 (Ticket AWX) ──depends on──► APIM-402 (Playbooks)
APIM-904 (Ticket AWX) ──depends on──► APIM-903 (Workflow)
APIM-905 (UI Tickets) ──depends on──► APIM-902 (API CRUD)
```

---

## Ordre d'Exécution Recommandé

### Sprint 1 (Semaines 1-2): Foundation
1. APIM-401 → APIM-402 → APIM-403 → APIM-404 → APIM-405
2. APIM-501 → APIM-502 (en parallèle)

### Sprint 2 (Semaines 3-4): Secrets + Ticketing
1. APIM-503 → APIM-504 → APIM-505
2. APIM-901 → APIM-902 → APIM-903 → APIM-904 → APIM-905

### Sprint 3 (Semaine 5): Multi-Env
1. APIM-601 → APIM-602 → APIM-603

### Sprint 4 (Semaines 5-6): Security Jobs
1. APIM-701, APIM-702, APIM-703, APIM-704 (parallélisables)

### Sprint 5-7 (Semaines 7-9): Developer Portal
1. APIM-801 → APIM-802 → APIM-803 → APIM-804 → APIM-805

---

## Notes

- Les estimations sont indicatives et peuvent varier selon la complexité réelle
- Les dépendances doivent être respectées pour éviter les blocages
- Chaque issue doit avoir des tests associés (non listés ici)
- La documentation doit être mise à jour à chaque phase complétée
