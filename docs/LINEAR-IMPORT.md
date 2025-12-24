# Linear Import - APIM Platform v2

## Configuration Linear

### Labels à créer

#### Par Phase
- `phase:4` - AWX Integration
- `phase:4.5` - Jenkins Orchestration
- `phase:5` - Vault Integration
- `phase:6` - Multi-Environment
- `phase:7` - Security Jobs
- `phase:8` - Developer Portal
- `phase:9` - Ticketing System
- `phase:10` - Resource Lifecycle
- `phase:11` - Resource Lifecycle Advanced

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
- `component:jenkins` - Jenkins Orchestration
- `component:terraform` - Infrastructure as Code
- `component:lambda` - AWS Lambda
- `component:n8n` - n8n Workflows
- `component:gatekeeper` - OPA Gatekeeper

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
| **M4: Cost Optimization** | Optimisation coûts et ressources | 10 |

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
| Phase 4.5 | Jenkins Orchestration | P0 | 1.5 semaines |
| Phase 5 | Vault Integration | P0 | 2 semaines |
| Phase 9 | Ticketing System | P0 | 1 semaine |
| Phase 6 | Multi-Environment | P1 | 2 semaines |
| Phase 7 | Security Batch Jobs | P1 | 1.5 semaines |
| Phase 8 | Developer Portal | P2 | 3 semaines |
| Phase 10 | Resource Lifecycle | P1 | 2 semaines |
| Phase 11 | Resource Lifecycle Advanced | P2 | 1.5 semaines |

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

### Phase 4.5 - Jenkins Orchestration Layer (P0)

#### APIM-451: Déploiement Jenkins sur EKS avec JCasC
```
Title: [Jenkins] Déploiement Jenkins sur EKS avec JCasC
Priority: P0 - Urgent
Labels: phase:4.5, type:infra, component:jenkins, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Déployer Jenkins sur EKS avec Jenkins Configuration as Code (JCasC) pour une configuration déclarative et reproductible.

Acceptance Criteria:
- [ ] Helm chart Jenkins déployé sur EKS
- [ ] JCasC configuré pour paramétrage automatique
- [ ] Persistent Volume pour JENKINS_HOME
- [ ] Agents Kubernetes dynamiques configurés
- [ ] Ingress configuré (jenkins.dev.apim.cab-i.com)
- [ ] Resource limits/requests définis
- [ ] Health checks (liveness/readiness)
- [ ] Backup automatique configuré
```

#### APIM-452: Intégration Keycloak OIDC pour Jenkins SSO
```
Title: [Jenkins] Intégration Keycloak OIDC pour SSO
Priority: P0 - Urgent
Labels: phase:4.5, type:security, component:jenkins, component:keycloak, priority:p0
Milestone: M1: Production-Ready
Estimate: 1 day

Description:
Configurer l'authentification Jenkins via Keycloak OIDC pour SSO unifié.

Acceptance Criteria:
- [ ] Plugin oic-auth installé
- [ ] Client Keycloak `apim-jenkins` créé
- [ ] Mapping rôles Keycloak → Jenkins:
  - cpi-admin → Jenkins Admin
  - tenant-admin → Jenkins User + approve
  - devops → Jenkins User
  - viewer → Jenkins Read-only
- [ ] Logout redirect vers Keycloak
- [ ] Groups claim configuré
- [ ] Tests SSO fonctionnels
```

#### APIM-453: Service Kafka Consumer → Jenkins Trigger
```
Title: [Jenkins] Service Kafka Consumer → Jenkins Job Trigger
Priority: P0 - Urgent
Labels: phase:4.5, type:integration, component:kafka, component:jenkins, priority:p0
Milestone: M1: Production-Ready
Estimate: 3 days

Description:
Développer le service Python qui consomme les events Kafka et déclenche les jobs Jenkins.

Event → Job Mapping:
- deploy-request → APIM/deploy-api
- promote-request → APIM/promote-api
- rollback-request → APIM/rollback-api
- delete-request → APIM/delete-api
- sync-request → APIM/sync-gateway

Acceptance Criteria:
- [ ] Consumer Python avec kafka-python
- [ ] Mapping event_type → Jenkins job
- [ ] API Jenkins Remote Build Trigger
- [ ] Token d'authentification sécurisé (Vault)
- [ ] Retry logic avec exponential backoff
- [ ] Dead letter queue pour events en échec
- [ ] Métriques Prometheus exposées
- [ ] Health check endpoint
- [ ] Tests unitaires pytest
```

#### APIM-454: Jenkinsfile Deploy API avec Approval Gates
```
Title: [Jenkins] Pipeline Deploy API avec Approval Gates production
Priority: P0 - Urgent
Labels: phase:4.5, type:feature, component:jenkins, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Créer le Jenkinsfile pour le déploiement d'API avec gates d'approbation pour la production.

Stages:
1. Validate (OpenAPI lint, security scan)
2. Approval Gate (prod uniquement, timeout 4h)
3. Deploy via AWX
4. Verify Deployment
5. Smoke Tests
6. Notify

Acceptance Criteria:
- [ ] Jenkinsfile `pipelines/deploy-api.groovy`
- [ ] Stage Validate avec OpenAPI linting
- [ ] Stage Approval Gate (input step)
- [ ] Submitters: cpi-admin, tenant-admin du tenant concerné
- [ ] Timeout 4 heures pour approbation
- [ ] Stage Deploy via AWX API
- [ ] Stage Verify avec health checks
- [ ] Stage Smoke tests
- [ ] Notifications Slack success/failure
- [ ] Audit trail complet
```

#### APIM-455: Jenkinsfile Rollback API
```
Title: [Jenkins] Pipeline Rollback API avec sécurité
Priority: High
Labels: phase:4.5, type:feature, component:jenkins, priority:p1
Milestone: M1: Production-Ready
Estimate: 1 day

Description:
Créer le Jenkinsfile pour le rollback d'API avec validation version cible.

Stages:
1. Get Previous Version
2. Validate Rollback Target
3. Rollback via AWX
4. Verify Rollback
5. Notify

Acceptance Criteria:
- [ ] Jenkinsfile `pipelines/rollback-api.groovy`
- [ ] Récupération version précédente depuis GitLab
- [ ] Validation version cible existe
- [ ] Rollback via AWX playbook
- [ ] Health check post-rollback
- [ ] Notification avec version source → cible
- [ ] Tests intégration
```

#### APIM-456: Jenkins Shared Library APIM
```
Title: [Jenkins] Shared Library fonctions réutilisables
Priority: High
Labels: phase:4.5, type:feature, component:jenkins, priority:p1
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Créer une Jenkins Shared Library avec les fonctions communes pour tous les pipelines APIM.

Fonctions:
- notifySlack(status, message)
- triggerAWX(jobTemplate, extraVars)
- waitAWXJob(jobId)
- validateOpenAPI(specPath)
- getGitLabFile(repo, path, ref)
- publishKafkaEvent(topic, event)

Acceptance Criteria:
- [ ] Repository GitLab `jenkins-shared-library`
- [ ] Structure vars/, src/, resources/
- [ ] Fonction notifySlack()
- [ ] Fonction triggerAWX() avec polling
- [ ] Fonction waitAWXJob() avec timeout
- [ ] Fonction validateOpenAPI()
- [ ] Fonction getGitLabFile()
- [ ] Fonction publishKafkaEvent()
- [ ] Tests unitaires Groovy
- [ ] Documentation usage
```

#### APIM-457: Intégration AWX depuis Jenkins
```
Title: [Jenkins] Intégration AWX Job Trigger depuis pipelines
Priority: P0 - Urgent
Labels: phase:4.5, type:integration, component:jenkins, component:awx, priority:p0
Milestone: M1: Production-Ready
Estimate: 2 days

Description:
Configurer l'intégration Jenkins → AWX pour déclencher les playbooks depuis les pipelines.

Acceptance Criteria:
- [ ] Credentials AWX dans Jenkins (via Vault)
- [ ] AWX API wrapper dans shared library
- [ ] Polling status job avec timeout
- [ ] Récupération logs AWX dans Jenkins console
- [ ] Gestion erreurs et retry
- [ ] Variables extra_vars passées au job
- [ ] Tests intégration Jenkins → AWX
```

#### APIM-458: Métriques et Dashboard Jenkins
```
Title: [Jenkins] Métriques Prometheus et Dashboard Grafana
Priority: Medium
Labels: phase:4.5, type:ui, component:jenkins, priority:p2
Milestone: M1: Production-Ready
Estimate: 1 day

Description:
Exposer les métriques Jenkins et créer un dashboard Grafana.

Métriques:
- jenkins_builds_total
- jenkins_build_duration_seconds
- jenkins_approval_wait_time_seconds
- jenkins_awx_trigger_total
- jenkins_queue_size

Acceptance Criteria:
- [ ] Plugin Prometheus Jenkins installé
- [ ] Métriques custom exposées
- [ ] ServiceMonitor Kubernetes
- [ ] Dashboard Grafana Jenkins
- [ ] Alertes build failure > 3
- [ ] Alertes queue > 10
```

#### APIM-459: Pipeline Sync Gateway Config
```
Title: [Jenkins] Pipeline Sync Gateway Configuration
Priority: Medium
Labels: phase:4.5, type:feature, component:jenkins, component:gateway, priority:p2
Milestone: M1: Production-Ready
Estimate: 1 day

Description:
Pipeline pour synchroniser la configuration du Gateway Kong depuis GitLab.

Stages:
1. Checkout config
2. Validate deck files
3. Diff preview
4. Apply via deck sync
5. Verify

Acceptance Criteria:
- [ ] Jenkinsfile `pipelines/sync-gateway.groovy`
- [ ] Checkout repo gateway-config
- [ ] Kong deck validate
- [ ] Kong deck diff (preview)
- [ ] Kong deck sync
- [ ] Health check post-sync
- [ ] Notification résultat
```

#### APIM-460: Blue Ocean UI et Job Organization
```
Title: [Jenkins] Blue Ocean UI et organisation jobs APIM
Priority: Low
Labels: phase:4.5, type:ui, component:jenkins, priority:p3
Milestone: M1: Production-Ready
Estimate: 1 day

Description:
Configurer Blue Ocean et organiser les jobs Jenkins pour une UX optimale.

Organisation:
- APIM/
  - deploy-api
  - rollback-api
  - promote-api
  - delete-api
  - sync-gateway
- Maintenance/
  - backup-jenkins
  - cleanup-old-builds

Acceptance Criteria:
- [ ] Plugin Blue Ocean installé
- [ ] Folder APIM créé
- [ ] Folder Maintenance créé
- [ ] Multibranch Pipeline pour chaque job
- [ ] Build history limit configuré (30 builds)
- [ ] Favoris par défaut pour jobs critiques
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

### Phase 10 - Resource Lifecycle Management (P1)

#### APIM-1001: Module Terraform common_tags
```
Title: [Terraform] Module common_tags avec validations
Priority: High
Labels: phase:10, type:infra, component:terraform, priority:p1
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Créer un module Terraform réutilisable pour standardiser le tagging de toutes les ressources AWS.

Tags obligatoires:
- environment (dev, staging, sandbox, demo, prod)
- owner (email valide)
- project (nom projet/tenant)
- cost-center (code centre de coût)
- ttl (7d, 14d, 30d max pour non-prod)
- created_at (auto-généré ISO 8601)
- auto-teardown (true/false)
- data-class (public, internal, confidential, restricted)

Acceptance Criteria:
- [ ] Module `terraform/modules/common_tags` créé
- [ ] Validation regex email pour owner
- [ ] Validation TTL max 30 jours
- [ ] Validation data-class enum
- [ ] Output `tags` avec tous les tags calculés
- [ ] Variable `managed-by: terraform` automatique
- [ ] Production exclue de l'auto-teardown automatiquement
- [ ] Documentation usage avec exemples
- [ ] Tests Terratest
```

#### APIM-1002: Lambda Resource Cleanup
```
Title: [Lambda] Job cleanup ressources expirées
Priority: High
Labels: phase:10, type:infra, component:lambda, priority:p1
Milestone: M4: Cost Optimization
Estimate: 3 days

Description:
Développer une Lambda Python pour supprimer automatiquement les ressources non-prod expirées.

Ressources supportées:
- EC2 instances
- RDS databases
- S3 buckets (avec vidage)
- EKS nodegroups
- EBS volumes orphelins

Acceptance Criteria:
- [ ] Lambda Python 3.11 avec boto3
- [ ] Query ressources avec tag `auto-teardown=true`
- [ ] Calcul expiration: created_at + ttl < now()
- [ ] Exclusion `data-class=restricted`
- [ ] Exclusion `environment=prod`
- [ ] Dry-run mode pour preview
- [ ] Logging structuré JSON
- [ ] Métriques CloudWatch (resources_deleted, errors)
- [ ] IAM role avec permissions minimales
- [ ] Tests unitaires pytest
```

#### APIM-1003: EventBridge Schedule
```
Title: [AWS] EventBridge schedule pour cleanup quotidien
Priority: High
Labels: phase:10, type:infra, priority:p1
Milestone: M4: Cost Optimization
Estimate: 1 day

Description:
Configurer EventBridge pour déclencher la Lambda de cleanup quotidiennement.

Acceptance Criteria:
- [ ] Rule EventBridge cron `0 2 * * ? *` (2h UTC)
- [ ] Target: Lambda resource-cleanup
- [ ] Retry policy configurée (2 retries)
- [ ] Dead letter queue SQS
- [ ] CloudWatch alarm si échec
- [ ] Terraform module pour déploiement
```

#### APIM-1004: Notifications Owner Expiration
```
Title: [Lambda] Notifications owner avant suppression
Priority: High
Labels: phase:10, type:feature, component:lambda, priority:p1
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Implémenter le système de notifications progressives avant suppression.

Workflow notifications:
1. J-2 (48h avant): Email warning "Votre ressource expire dans 48h"
2. J-1 (24h avant): Email urgent "Suppression imminente dans 24h"
3. J-0: Suppression + email confirmation

Acceptance Criteria:
- [ ] Lambda notification séparée
- [ ] Templates email HTML (48h, 24h, deleted)
- [ ] SES configuré pour envoi emails
- [ ] Lien "Extend TTL" dans l'email (optionnel)
- [ ] Historique notifications en DynamoDB
- [ ] Intégration Slack webhook (optionnel)
- [ ] Tests avec emails mock
```

#### APIM-1005: OPA Gatekeeper Policies
```
Title: [K8s] OPA Gatekeeper policies pour tags obligatoires
Priority: High
Labels: phase:10, type:security, component:gatekeeper, priority:p1
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Implémenter des policies Gatekeeper pour rejeter les deployments K8s sans tags obligatoires.

Acceptance Criteria:
- [ ] ConstraintTemplate `K8sRequiredTags`
- [ ] Constraint pour Namespaces
- [ ] Constraint pour Deployments/StatefulSets
- [ ] Constraint pour Pods
- [ ] Exclusions: kube-system, gatekeeper-system, apim-system
- [ ] Message d'erreur explicite avec tags manquants
- [ ] Mode audit avant enforcement
- [ ] Documentation pour équipes dev
```

#### APIM-1006: GitHub Actions Tag Governance
```
Title: [CI] GitHub Actions workflow tag-governance
Priority: Medium
Labels: phase:10, type:infra, priority:p2
Milestone: M4: Cost Optimization
Estimate: 1 day

Description:
Créer un workflow GitHub Actions pour valider les tags avant merge.

Acceptance Criteria:
- [ ] Workflow `.github/workflows/tag-governance.yaml`
- [ ] Trigger sur PR modifiant `terraform/**` ou `k8s/**`
- [ ] Check: tous resources utilisent module.tags.tags
- [ ] Check: TTL <= 30d pour non-prod
- [ ] Check: data-class valide
- [ ] Annotations PR avec erreurs détaillées
- [ ] Status check bloquant pour merge
```

#### APIM-1007: Kafka Events Resource Lifecycle
```
Title: [Kafka] Topics et events resource lifecycle
Priority: Medium
Labels: phase:10, type:integration, component:kafka, priority:p2
Milestone: M4: Cost Optimization
Estimate: 1 day

Description:
Créer les topics Kafka pour l'audit du cycle de vie des ressources.

Topics:
- `resource-created`: Log création avec tags complets
- `resource-expiring`: Notification 48h/24h avant expiration
- `resource-deleted`: Audit trail suppression
- `tag-violation`: Alerte déploiement sans tags

Acceptance Criteria:
- [ ] Topics créés dans Redpanda
- [ ] Schema Avro pour chaque event type
- [ ] Producer dans Lambda cleanup
- [ ] Consumer OpenSearch pour indexation
- [ ] Retention 90 jours
- [ ] Documentation schema events
```

#### APIM-1008: Dashboard Grafana Resource Lifecycle
```
Title: [Grafana] Dashboard Resource Lifecycle
Priority: Medium
Labels: phase:10, type:ui, priority:p2
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Créer un dashboard Grafana pour visualiser le cycle de vie des ressources.

Acceptance Criteria:
- [ ] Panel: Ressources par environnement (pie chart)
- [ ] Panel: Ressources expirant cette semaine (table)
- [ ] Panel: Ressources supprimées (timeline)
- [ ] Panel: Coûts évités estimés
- [ ] Panel: Top owners par ressources
- [ ] Panel: Violations tags (gauge)
- [ ] Alertes Grafana si cleanup échoue
- [ ] Export JSON du dashboard
```

#### APIM-1009: n8n Workflow Multi-Cloud (Optionnel)
```
Title: [n8n] Workflow cleanup multi-cloud
Priority: Low
Labels: phase:10, type:integration, component:n8n, priority:p3
Milestone: M4: Cost Optimization
Estimate: 3 days

Description:
Alternative à Lambda pour environnements multi-cloud (AWS + Azure + GCP).

Acceptance Criteria:
- [ ] n8n déployé sur EKS (Helm chart)
- [ ] Workflow "Resource Cleanup" avec nodes:
  - Schedule Trigger (cron 2h UTC)
  - AWS Node (EC2, RDS, S3)
  - Azure Node (VMs, SQL, Storage) - optionnel
  - GCP Node (Compute, Cloud SQL) - optionnel
  - Slack Node (notifications)
  - HTTP Node (Kafka events)
- [ ] Credentials stockés dans Vault
- [ ] UI accessible pour monitoring
- [ ] Export workflow JSON
```

#### APIM-1010: Documentation Tagging Policy
```
Title: [Docs] Documentation politique de tagging
Priority: Medium
Labels: phase:10, type:docs, priority:p2
Milestone: M4: Cost Optimization
Estimate: 1 day

Description:
Rédiger la documentation complète de la politique de tagging.

Acceptance Criteria:
- [ ] Guide `docs/TAGGING-POLICY.md` créé
- [ ] Section: Tags obligatoires (description, valeurs)
- [ ] Section: Guardrails et exceptions
- [ ] Section: Workflow auto-teardown
- [ ] Section: Comment étendre un TTL
- [ ] Section: FAQ
- [ ] Diagrammes Mermaid inclus
- [ ] Lien depuis README principal
```

---

### Phase 11 - Resource Lifecycle Advanced (P2)

#### APIM-1101: Quotas par Projet
```
Title: [Terraform] Système de quotas par projet/tenant
Priority: Medium
Labels: phase:11, type:infra, component:terraform, priority:p2
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Implémenter un système de quotas configurables par projet pour limiter la création de ressources.

Quotas par défaut:
- EC2 Instances: 10
- RDS Databases: 3
- S3 Buckets: 5
- Lambda Functions: 20
- K8s Namespaces: 5
- EBS Volumes: 500 GB

Acceptance Criteria:
- [ ] Module Terraform `project_quotas`
- [ ] Configuration quotas par tenant dans YAML
- [ ] Intégration AWS Service Quotas
- [ ] Validation pré-déploiement (Terraform plan)
- [ ] OPA policy K8s pour quotas namespaces
- [ ] Alertes si quota atteint à 80%
- [ ] Dashboard quotas par projet
```

#### APIM-1102: Whitelist Never Delete
```
Title: [Config] Whitelist ressources à ne jamais supprimer
Priority: High
Labels: phase:11, type:security, priority:p1
Milestone: M4: Cost Optimization
Estimate: 1 day

Description:
Configurer une whitelist de ressources critiques exclues de l'auto-teardown.

Acceptance Criteria:
- [ ] Fichier `config/whitelist.yaml`
- [ ] Support ARN patterns (wildcards)
- [ ] Support tag `critical=true`
- [ ] Support namespaces K8s
- [ ] Validation au démarrage Lambda
- [ ] Logging ressources skippées
- [ ] UI pour voir/éditer whitelist
```

#### APIM-1103: Destruction Ordonnée
```
Title: [Lambda] Destruction ordonnée avec dépendances
Priority: High
Labels: phase:11, type:infra, component:lambda, priority:p1
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Implémenter la destruction ordonnée des ressources pour respecter les dépendances AWS.

Ordre de destruction:
1. Detach IAM Policies/Roles
2. Stop Auto Scaling Groups
3. Terminate EC2 Instances
4. Delete Load Balancers
5. Empty & Delete S3 Buckets
6. Delete RDS Snapshots
7. Delete RDS Instances
8. Delete EBS Volumes orphelins
9. Delete Security Groups
10. Delete K8s Namespaces

Acceptance Criteria:
- [ ] DESTRUCTION_ORDER configurable
- [ ] Handler par type de ressource
- [ ] Gestion erreurs (continue on error)
- [ ] Retry avec backoff
- [ ] Logging détaillé par étape
- [ ] Métriques par type de ressource
- [ ] Dry-run mode
```

#### APIM-1104: API Self-Service TTL Extension
```
Title: [API] Endpoint self-service extension TTL
Priority: Medium
Labels: phase:11, type:api, component:api, priority:p2
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Permettre aux owners d'étendre le TTL de leurs ressources via API.

Endpoint: PATCH /v1/resources/{id}/ttl
Body: { "extend_days": 7, "reason": "Tests en cours" }

Acceptance Criteria:
- [ ] Endpoint PATCH /v1/resources/{id}/ttl
- [ ] Vérification ownership (owner == user.email)
- [ ] Limite 2 extensions max (60j total)
- [ ] Extensions autorisées: 7j ou 14j
- [ ] Event Kafka `resource-ttl-extended`
- [ ] Audit trail complet
- [ ] Tests unitaires + intégration
```

#### APIM-1105: Boutons Snooze dans Emails
```
Title: [Lambda] Boutons Snooze dans emails pré-alerte
Priority: Medium
Labels: phase:11, type:feature, component:lambda, priority:p2
Milestone: M4: Cost Optimization
Estimate: 1 day

Description:
Ajouter des boutons d'action dans les emails de pré-alerte.

Boutons:
- [Snooze +7 jours]
- [Snooze +14 jours]
- [Supprimer maintenant]

Acceptance Criteria:
- [ ] Template email HTML avec boutons
- [ ] Liens sécurisés (token JWT one-time)
- [ ] Expiration liens 48h
- [ ] Endpoint `/v1/resources/{id}/snooze?token=xxx&days=7`
- [ ] Confirmation visuelle après clic
- [ ] Logging des actions
```

#### APIM-1106: Calcul Coût Évité
```
Title: [Lambda] Calculateur coût évité par suppression
Priority: Medium
Labels: phase:11, type:feature, component:lambda, priority:p2
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Calculer et reporter le coût évité par la suppression automatique.

Pricing à intégrer:
- EC2: instance_type → prix horaire AWS
- RDS: db_instance_class × multi-AZ factor
- S3: storage_gb × $0.023/GB
- EBS: volume_size × $0.10/GB/month

Acceptance Criteria:
- [ ] Mapping instance_type → hourly_rate
- [ ] Calcul: rate × remaining_hours
- [ ] Métriques Prometheus `cost_avoided_usd`
- [ ] Agrégation par project, environment
- [ ] Event Kafka `resource-deleted` avec cost_avoided
- [ ] Refresh pricing mensuel (optionnel)
```

#### APIM-1107: Dashboard Cost Savings
```
Title: [Grafana] Dashboard Cost Savings
Priority: Medium
Labels: phase:11, type:ui, priority:p2
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Dashboard Grafana pour visualiser les économies réalisées.

Panels:
- Coût évité ce mois (gauge)
- Coût évité par projet (bar chart)
- Ressources supprimées (timeline)
- Top 5 projets économies
- Ressources snooze vs deleted (pie)
- Violations tags (counter)

Acceptance Criteria:
- [ ] Dashboard JSON exportable
- [ ] Datasource Prometheus
- [ ] Variables: project, environment, time_range
- [ ] Alertes si coût évité < seuil
- [ ] Export PDF mensuel automatique
```

#### APIM-1108: n8n Workflow avec Notion
```
Title: [n8n] Workflow complet avec Notion board
Priority: Low
Labels: phase:11, type:integration, component:n8n, priority:p3
Milestone: M4: Cost Optimization
Estimate: 2 days

Description:
Workflow n8n complet avec intégration Notion pour tracking.

Nodes:
- Schedule Trigger (cron horaire)
- AWS: Describe resources
- Function: Check whitelist + expiry
- IF: expiring_in_48h
- Slack: Pre-alert
- Notion: Add to "Resources to Delete" database
- Wait: 24h
- IF: not_snoozed
- Function: Ordered destruction
- HTTP: /v1/events/resource-deleted
- Notion: Mark as deleted
- Slack: Deletion report

Acceptance Criteria:
- [ ] Workflow n8n exporté (.json)
- [ ] Database Notion "Resources to Delete"
- [ ] Propriétés: resource_id, type, owner, expires_at, status
- [ ] Vue Kanban par status
- [ ] Bouton "Snooze" dans Notion
- [ ] Documentation setup n8n
```

#### APIM-1109: Cron Horaire Pre-Alertes
```
Title: [Lambda] Cron horaire pour pré-alertes précises
Priority: Low
Labels: phase:11, type:infra, priority:p3
Milestone: M4: Cost Optimization
Estimate: 1 day

Description:
Passer de cron quotidien à horaire pour des notifications plus précises.

Schedule: 0 * * * ? * (toutes les heures)

Acceptance Criteria:
- [ ] EventBridge rule hourly
- [ ] Lambda optimisée (cache résultats)
- [ ] Déduplication notifications (max 1/24h par ressource)
- [ ] DynamoDB pour tracking notifications envoyées
- [ ] Métriques: notifications_sent_hourly
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
# Phase 4 → Phase 4.5
APIM-403 (Kafka Consumer) ──depends on──► APIM-402 (Playbooks)
APIM-404 (Callback) ──depends on──► APIM-403 (Consumer)
APIM-405 (UI AWX) ──depends on──► APIM-404 (Callback)

# Phase 4.5 Jenkins
APIM-452 (Keycloak SSO) ──depends on──► APIM-451 (Jenkins Deploy)
APIM-453 (Kafka Consumer Jenkins) ──depends on──► APIM-451 (Jenkins Deploy)
APIM-454 (Deploy Pipeline) ──depends on──► APIM-456 (Shared Library)
APIM-454 (Deploy Pipeline) ──depends on──► APIM-457 (AWX Integration)
APIM-455 (Rollback Pipeline) ──depends on──► APIM-456 (Shared Library)
APIM-457 (AWX Integration) ──depends on──► APIM-402 (Playbooks AWX)
APIM-458 (Métriques Jenkins) ──depends on──► APIM-451 (Jenkins Deploy)
APIM-459 (Sync Gateway) ──depends on──► APIM-456 (Shared Library)
APIM-460 (Blue Ocean) ──depends on──► APIM-454 (Deploy Pipeline)

APIM-504 (AWX Vault) ──depends on──► APIM-501 (Vault Config)
APIM-504 (AWX Vault) ──depends on──► APIM-402 (Playbooks)
APIM-505 (UI Secrets) ──depends on──► APIM-503 (API Secrets)

APIM-904 (Ticket AWX) ──depends on──► APIM-402 (Playbooks)
APIM-904 (Ticket AWX) ──depends on──► APIM-903 (Workflow)
APIM-905 (UI Tickets) ──depends on──► APIM-902 (API CRUD)

APIM-1002 (Lambda) ──depends on──► APIM-1001 (Tags Module)
APIM-1003 (EventBridge) ──depends on──► APIM-1002 (Lambda)
APIM-1004 (Notifications) ──depends on──► APIM-1002 (Lambda)
APIM-1007 (Kafka Events) ──depends on──► APIM-1002 (Lambda)
APIM-1008 (Grafana) ──depends on──► APIM-1007 (Kafka Events)
APIM-1009 (n8n) ──depends on──► APIM-1001 (Tags Module) [Alternative]

# Phase 11 dépendances
APIM-1102 (Whitelist) ──depends on──► APIM-1002 (Lambda Cleanup)
APIM-1103 (Ordered Destroy) ──depends on──► APIM-1002 (Lambda Cleanup)
APIM-1104 (TTL Extension) ──depends on──► APIM-1004 (Notifications)
APIM-1105 (Boutons Snooze) ──depends on──► APIM-1104 (TTL Extension)
APIM-1106 (Cost Calculator) ──depends on──► APIM-1002 (Lambda Cleanup)
APIM-1107 (Cost Dashboard) ──depends on──► APIM-1106 (Cost Calculator)
APIM-1108 (n8n Notion) ──depends on──► APIM-1009 (n8n Basic)
APIM-1109 (Cron Hourly) ──depends on──► APIM-1003 (EventBridge)
```

---

## Ordre d'Exécution Recommandé

### Sprint 1 (Semaines 1-2): AWX Foundation
1. APIM-401 → APIM-402 → APIM-403 → APIM-404 → APIM-405
2. APIM-501 → APIM-502 (en parallèle)

### Sprint 1.5 (Semaine 2-3): Jenkins Orchestration
1. APIM-451 → APIM-452 (Deploy + SSO)
2. APIM-456 → APIM-457 (Shared Library + AWX Integration)
3. APIM-453 (Kafka Consumer Jenkins)
4. APIM-454 → APIM-455 (Pipelines Deploy + Rollback)
5. APIM-458, APIM-459, APIM-460 (parallélisables)

### Sprint 2 (Semaines 4-5): Secrets + Ticketing
1. APIM-503 → APIM-504 → APIM-505
2. APIM-901 → APIM-902 → APIM-903 → APIM-904 → APIM-905

### Sprint 3 (Semaine 5): Multi-Env
1. APIM-601 → APIM-602 → APIM-603

### Sprint 4 (Semaines 5-6): Security Jobs
1. APIM-701, APIM-702, APIM-703, APIM-704 (parallélisables)

### Sprint 5-7 (Semaines 7-9): Developer Portal
1. APIM-801 → APIM-802 → APIM-803 → APIM-804 → APIM-805

### Sprint 8-9 (Semaines 10-11): Resource Lifecycle (Phase 10)
1. APIM-1001 → APIM-1002 → APIM-1003 (séquentiel)
2. APIM-1004, APIM-1005, APIM-1006 (parallélisables après APIM-1002)
3. APIM-1007 → APIM-1008 (séquentiel)
4. APIM-1009 (optionnel, si multi-cloud requis)
5. APIM-1010 (documentation, en continu)

### Sprint 10 (Semaines 12-13): Resource Lifecycle Advanced (Phase 11)
1. APIM-1101 (Quotas) - indépendant
2. APIM-1102 → APIM-1103 (Whitelist → Ordered Destroy)
3. APIM-1104 → APIM-1105 (TTL Extension → Snooze Buttons)
4. APIM-1106 → APIM-1107 (Cost Calculator → Dashboard)
5. APIM-1108 (n8n Notion) - après Phase 10 APIM-1009
6. APIM-1109 (Cron Hourly) - optionnel

---

## Notes

- Les estimations sont indicatives et peuvent varier selon la complexité réelle
- Les dépendances doivent être respectées pour éviter les blocages
- Chaque issue doit avoir des tests associés (non listés ici)
- La documentation doit être mise à jour à chaque phase complétée
