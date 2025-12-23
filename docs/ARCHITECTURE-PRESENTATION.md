# APIM Platform v2 - Architecture Finale

## Présentation Exécutive

**APIM Platform v2** est une plateforme de gestion d'APIs multi-tenant conçue pour l'entreprise, intégrant les meilleures pratiques DevOps, GitOps et Event-Driven Architecture.

---

## Vue d'Ensemble

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              APIM PLATFORM v2                                            │
│                         Event-Driven API Management                                      │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                            CONTROL PLANE                                         │   │
│   │                                                                                  │   │
│   │   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                    │   │
│   │   │  UI DevOps   │     │  REST API    │     │   GitLab     │                    │   │
│   │   │   (React)    │────▶│  (FastAPI)   │────▶│   (GitOps)   │                    │   │
│   │   │              │     │              │     │              │                    │   │
│   │   └──────────────┘     └──────┬───────┘     └──────────────┘                    │   │
│   │                               │                                                  │   │
│   └───────────────────────────────┼──────────────────────────────────────────────────┘   │
│                                   │                                                      │
│   ┌───────────────────────────────▼──────────────────────────────────────────────────┐   │
│   │                                                                                  │   │
│   │                    ██╗  ██╗ █████╗ ███████╗██╗  ██╗ █████╗                       │   │
│   │                    ██║ ██╔╝██╔══██╗██╔════╝██║ ██╔╝██╔══██╗                      │   │
│   │                    █████╔╝ ███████║█████╗  █████╔╝ ███████║                      │   │
│   │                    ██╔═██╗ ██╔══██║██╔══╝  ██╔═██╗ ██╔══██║                      │   │
│   │                    ██║  ██╗██║  ██║██║     ██║  ██╗██║  ██║                      │   │
│   │                    ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝                      │   │
│   │                                                                                  │   │
│   │                         EVENT STREAMING HUB                                      │   │
│   │                        (Redpanda - Kafka API)                                    │   │
│   │                                                                                  │   │
│   └───────────────────────────────┬──────────────────────────────────────────────────┘   │
│                                   │                                                      │
│           ┌───────────────────────┼───────────────────────┐                             │
│           │                       │                       │                             │
│           ▼                       ▼                       ▼                             │
│   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐                      │
│   │     AWX      │        │   ArgoCD     │        │  OpenSearch  │                      │
│   │  (Ansible)   │        │   (GitOps)   │        │ (Analytics)  │                      │
│   │              │        │              │        │              │                      │
│   └──────┬───────┘        └──────────────┘        └──────────────┘                      │
│          │                                                                               │
│          ▼                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                            DATA PLANE                                            │   │
│   │                                                                                  │   │
│   │   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                    │   │
│   │   │  webMethods  │     │  Developer   │     │    Vault     │                    │   │
│   │   │   Gateway    │◀───▶│    Portal    │     │  (Secrets)   │                    │   │
│   │   │              │     │              │     │              │                    │   │
│   │   └──────────────┘     └──────────────┘     └──────────────┘                    │   │
│   │                                                                                  │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Pourquoi Kafka ? Le Coeur de l'Architecture

### Le Problème Sans Kafka

```
                    ARCHITECTURE SYNCHRONE (Anti-Pattern)
                    ══════════════════════════════════════

    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
    │   UI    │────▶│   API   │────▶│   AWX   │────▶│ Gateway │
    └─────────┘     └─────────┘     └─────────┘     └─────────┘
         │               │               │               │
         │               │               │               │
         ▼               ▼               ▼               ▼
    ⏳ Attente      ⏳ Bloqué       ⏳ Timeout      ❌ Échec

    Problèmes:
    ❌ Couplage fort entre services
    ❌ Timeout en cascade (API attend AWX qui attend Gateway)
    ❌ Pas de retry automatique
    ❌ Perte de données si un service tombe
    ❌ Impossible de scaler indépendamment
    ❌ Un service lent bloque tout le pipeline
```

### La Solution Avec Kafka

```
                    ARCHITECTURE EVENT-DRIVEN (Best Practice)
                    ═══════════════════════════════════════════

    ┌─────────┐     ┌─────────┐     ┌─────────────────────────────────────┐
    │   UI    │────▶│   API   │────▶│              KAFKA                  │
    └─────────┘     └─────────┘     │                                     │
         │               │          │  ┌─────────────────────────────┐    │
         │          ✅ Retour       │  │     TOPICS                  │    │
         │          immédiat        │  │                             │    │
         ▼               │          │  │  api-created ──────────┐   │    │
    ✅ Réponse          │          │  │  api-updated ──────────┤   │    │
    instantanée          │          │  │  deploy-requests ──────┤   │    │
                         │          │  │  deploy-results ───────┤   │    │
                         │          │  │  audit-log ────────────┤   │    │
                         │          │  │  notifications ────────┤   │    │
                         │          │  │  security-job-results ─┘   │    │
                         │          │  │                             │    │
                         │          │  └─────────────────────────────┘    │
                         │          │                                     │
                         │          └──────────────┬──────────────────────┘
                         │                         │
                         │          ┌──────────────┴──────────────┐
                         │          │                             │
                         │          ▼                             ▼
                         │   ┌─────────────┐              ┌─────────────┐
                         │   │     AWX     │              │  OpenSearch │
                         │   │  Consumer   │              │  Consumer   │
                         │   └──────┬──────┘              └─────────────┘
                         │          │
                         │          ▼
                         │   ┌─────────────┐
                         │   │   Gateway   │
                         │   └─────────────┘
                         │          │
                         │          ▼
                         └────▶ Notification
                               (via Kafka)

    Avantages:
    ✅ Découplage total des services
    ✅ Réponse immédiate à l'utilisateur
    ✅ Retry automatique (Kafka retention)
    ✅ Aucune perte de données (persistance)
    ✅ Scaling horizontal de chaque consumer
    ✅ Traçabilité complète (event sourcing)
```

---

## Topics Kafka - Vue Détaillée

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              KAFKA TOPICS ARCHITECTURE                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                           LIFECYCLE EVENTS                                          │ │
│  │                                                                                     │ │
│  │   api-created          api-updated          api-deleted                            │ │
│  │   ────────────         ────────────         ────────────                           │ │
│  │   {                    {                    {                                      │ │
│  │     "api_id": "...",     "api_id": "...",     "api_id": "...",                    │ │
│  │     "tenant": "...",     "changes": [...],    "deleted_by": "..."                 │ │
│  │     "created_by": ".."   "updated_by": ".."   "timestamp": "..."                  │ │
│  │   }                    }                    }                                      │ │
│  │                                                                                     │ │
│  │   Producers: Control-Plane API                                                     │ │
│  │   Consumers: ArgoCD, Audit, Notifications                                          │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                          DEPLOYMENT PIPELINE                                        │ │
│  │                                                                                     │ │
│  │   deploy-requests                          deploy-results                          │ │
│  │   ─────────────────                        ──────────────────                      │ │
│  │   {                                        {                                       │ │
│  │     "trace_id": "trc-123",                   "trace_id": "trc-123",               │ │
│  │     "api_id": "payment-api",                 "status": "success",                 │ │
│  │     "environment": "dev",                    "awx_job_id": 456,                   │ │
│  │     "action": "deploy",                      "duration_ms": 4523,                 │ │
│  │     "triggered_by": "gitlab-push"            "gateway_response": {...}            │ │
│  │   }                                        }                                       │ │
│  │                                                                                     │ │
│  │   Producer: Control-Plane API              Producer: AWX Worker                    │ │
│  │   Consumer: AWX Worker                     Consumer: Control-Plane API             │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                           OBSERVABILITY                                             │ │
│  │                                                                                     │ │
│  │   audit-log                    notifications              security-job-results    │ │
│  │   ─────────────                ─────────────              ────────────────────     │ │
│  │   {                            {                          {                        │ │
│  │     "action": "API_CREATED",     "type": "deploy_success",  "job_name": "cert-chk",│ │
│  │     "actor": "user@...",         "recipients": [...],       "status": "success",  │ │
│  │     "resource": "...",           "template": "...",         "findings": [...]     │ │
│  │     "ip": "10.0.1.x"             "data": {...}            }                        │ │
│  │   }                            }                                                   │ │
│  │                                                                                     │ │
│  │   Consumers: OpenSearch, Compliance                                                │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Flux de Déploiement - Event-Driven

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT FLOW - EVENT DRIVEN                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  1. TRIGGER                                                                              │
│  ═════════                                                                               │
│                                                                                          │
│     ┌──────────────┐          ┌──────────────┐          ┌──────────────┐               │
│     │   GitLab     │   push   │  Control-    │  publish │    Kafka     │               │
│     │   Webhook    │─────────▶│  Plane API   │─────────▶│  (deploy-    │               │
│     │              │          │              │          │   requests)  │               │
│     └──────────────┘          └──────────────┘          └──────┬───────┘               │
│                                      │                         │                        │
│                               ✅ 200 OK                        │                        │
│                           (< 100ms)                            │                        │
│                                                                │                        │
│  2. PROCESSING (Asynchrone)                                    │                        │
│  ══════════════════════════                                    │                        │
│                                                                ▼                        │
│                                                         ┌──────────────┐               │
│     ┌──────────────┐                                    │     AWX      │               │
│     │   Gateway    │◀───────── Ansible Playbook ────────│   Consumer   │               │
│     │   (Deploy)   │                                    │              │               │
│     └──────┬───────┘                                    └──────┬───────┘               │
│            │                                                   │                        │
│            │                                                   │                        │
│  3. RESULT                                                     │                        │
│  ════════                                                      │                        │
│            │                                                   │                        │
│            └───────────────────────┬───────────────────────────┘                        │
│                                    │                                                    │
│                                    ▼                                                    │
│                             ┌──────────────┐                                           │
│                             │    Kafka     │                                           │
│                             │  (deploy-    │                                           │
│                             │   results)   │                                           │
│                             └──────┬───────┘                                           │
│                                    │                                                    │
│            ┌───────────────────────┼───────────────────────┐                           │
│            │                       │                       │                           │
│            ▼                       ▼                       ▼                           │
│     ┌──────────────┐        ┌──────────────┐        ┌──────────────┐                  │
│     │  Control-    │        │  OpenSearch  │        │ Notification │                  │
│     │  Plane API   │        │  (Traces)    │        │   Service    │                  │
│     │  (Update UI) │        │              │        │  (Slack...)  │                  │
│     └──────────────┘        └──────────────┘        └──────────────┘                  │
│                                                                                          │
│  TIMELINE                                                                                │
│  ════════                                                                                │
│                                                                                          │
│  0s        100ms                            30s                      45s                │
│  │          │                                │                        │                 │
│  ├──────────┼────────────────────────────────┼────────────────────────┤                │
│  │          │                                │                        │                 │
│  Webhook    API OK                      AWX Job                  Complete               │
│  Received   (Async)                     Running                  + Notify               │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Avantages Clés de Kafka

### 1. Découplage & Résilience

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESILIENCE PATTERN                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   SCENARIO: AWX est indisponible pendant 2 heures               │
│                                                                  │
│   SANS KAFKA:                                                    │
│   ───────────                                                    │
│   ❌ Tous les déploiements échouent                             │
│   ❌ Les utilisateurs voient des erreurs                        │
│   ❌ Données perdues, retry manuel nécessaire                   │
│                                                                  │
│   AVEC KAFKA:                                                    │
│   ───────────                                                    │
│   ✅ Les events sont stockés dans le topic                      │
│   ✅ L'API répond "accepted" immédiatement                      │
│   ✅ AWX revient → consomme tous les events en attente          │
│   ✅ Aucune perte, aucune intervention manuelle                 │
│                                                                  │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐  │
│   │ Event 1 │     │ Event 2 │     │ Event 3 │     │ Event 4 │  │
│   │ 10:00   │     │ 10:15   │     │ 10:30   │     │ 10:45   │  │
│   └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘  │
│        │               │               │               │        │
│        └───────────────┴───────────────┴───────────────┘        │
│                              │                                   │
│                    Kafka Retention (7 jours)                     │
│                              │                                   │
│                              ▼                                   │
│                     ┌───────────────┐                           │
│                     │  AWX revient  │                           │
│                     │  à 12:00      │                           │
│                     │               │                           │
│                     │  Traite les   │                           │
│                     │  4 events     │                           │
│                     └───────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Scalabilité Horizontale

```
┌─────────────────────────────────────────────────────────────────┐
│                    SCALING PATTERN                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Topic: deploy-requests (6 partitions)                         │
│                                                                  │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│   │ Part 0  │ │ Part 1  │ │ Part 2  │ │ Part 3  │ │ Part 4  │  │
│   │ ████    │ │ ██      │ │ ███     │ │ █       │ │ ████    │  │
│   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘  │
│        │           │           │           │           │        │
│        │           │           │           │           │        │
│   AVANT (1 consumer)                                            │
│   ──────────────────                                            │
│        │           │           │           │           │        │
│        └───────────┴───────────┴───────────┴───────────┘        │
│                              │                                   │
│                    ┌─────────────────┐                          │
│                    │  AWX Worker 1   │  ← Surcharge!            │
│                    │  (toutes parts) │                          │
│                    └─────────────────┘                          │
│                                                                  │
│   APRES (3 consumers - Consumer Group)                          │
│   ────────────────────────────────────                          │
│        │           │           │           │           │        │
│        └─────┬─────┘           │           └─────┬─────┘        │
│              │                 │                 │               │
│              ▼                 ▼                 ▼               │
│   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐  │
│   │  AWX Worker 1   │ │  AWX Worker 2   │ │  AWX Worker 3   │  │
│   │  (Part 0, 1)    │ │  (Part 2, 3)    │ │  (Part 4, 5)    │  │
│   └─────────────────┘ └─────────────────┘ └─────────────────┘  │
│                                                                  │
│   Résultat: 3x plus de throughput, automatiquement réparti     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Event Sourcing & Audit

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUDIT & COMPLIANCE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Topic: audit-log (retention: 1 an, compaction: key)           │
│                                                                  │
│   Chaque action est un event immuable:                          │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Offset 1001 │ 2024-12-21 10:15:23                       │   │
│   │             │                                            │   │
│   │ {                                                        │   │
│   │   "event_type": "API_CREATED",                          │   │
│   │   "actor": {                                             │   │
│   │     "user_id": "jean.dupont@cab-i.com",                 │   │
│   │     "ip": "10.0.1.45",                                  │   │
│   │     "tenant": "tenant-finance"                          │   │
│   │   },                                                     │   │
│   │   "resource": {                                          │   │
│   │     "type": "API",                                       │   │
│   │     "id": "payment-api",                                 │   │
│   │     "version": "1.0.0"                                   │   │
│   │   },                                                     │   │
│   │   "changes": {                                           │   │
│   │     "backend_url": "https://payment.internal..."        │   │
│   │   },                                                     │   │
│   │   "git_commit": "abc123"                                 │   │
│   │ }                                                        │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   Avantages:                                                     │
│   ✅ Traçabilité complète (qui, quoi, quand)                    │
│   ✅ Replay possible (reconstuire l'état)                       │
│   ✅ Conformité réglementaire (audit trail)                     │
│   ✅ Forensics en cas d'incident                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Multi-Consumer Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-CONSUMER PATTERN                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Un seul event "api-created" déclenche N actions parallèles:   │
│                                                                  │
│                      ┌──────────────────┐                       │
│                      │   Control-Plane  │                       │
│                      │       API        │                       │
│                      └────────┬─────────┘                       │
│                               │                                  │
│                               │ publish                          │
│                               ▼                                  │
│                      ┌──────────────────┐                       │
│                      │   api-created    │                       │
│                      │     (Topic)      │                       │
│                      └────────┬─────────┘                       │
│                               │                                  │
│         ┌─────────────────────┼─────────────────────┐           │
│         │                     │                     │           │
│         ▼                     ▼                     ▼           │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐     │
│  │   ArgoCD    │      │  OpenSearch │      │   Slack     │     │
│  │   Sync      │      │   Index     │      │   Notify    │     │
│  │             │      │             │      │             │     │
│  │ Consumer    │      │ Consumer    │      │ Consumer    │     │
│  │ Group: sync │      │ Group: idx  │      │ Group: ntfy │     │
│  └─────────────┘      └─────────────┘      └─────────────┘     │
│         │                     │                     │           │
│         ▼                     ▼                     ▼           │
│  Déploie sur K8s      Indexe pour        Notifie l'équipe      │
│                       recherche                                 │
│                                                                  │
│   Chaque consumer group lit TOUT le topic indépendamment       │
│   → Ajout d'un nouveau consumer = 0 impact sur les autres      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Redpanda vs Apache Kafka

```
┌─────────────────────────────────────────────────────────────────┐
│                    POURQUOI REDPANDA ?                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                                                          │   │
│   │   100% COMPATIBLE API KAFKA                              │   │
│   │   ══════════════════════════                             │   │
│   │                                                          │   │
│   │   • Même protocole, mêmes clients                        │   │
│   │   • kafka-python, librdkafka fonctionnent               │   │
│   │   • Migration transparente                               │   │
│   │                                                          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌──────────────────────┬──────────────────────┐               │
│   │   Apache Kafka       │   Redpanda           │               │
│   ├──────────────────────┼──────────────────────┤               │
│   │   JVM (Java)         │   C++ natif          │               │
│   │   ZooKeeper requis*  │   No ZooKeeper       │               │
│   │   3+ nodes min       │   1 node possible    │               │
│   │   ~2GB RAM min       │   ~500MB RAM         │               │
│   │   Config complexe    │   Config simple      │               │
│   │   Latence ~10ms      │   Latence ~1ms       │               │
│   └──────────────────────┴──────────────────────┘               │
│   * KRaft mode disponible depuis Kafka 3.x                      │
│                                                                  │
│   POUR NOTRE CAS (EKS avec ressources limitées):                │
│   ───────────────────────────────────────────────               │
│   ✅ Redpanda = moins de ressources                             │
│   ✅ Redpanda = déploiement simplifié                           │
│   ✅ Redpanda Console incluse (UI admin)                        │
│   ✅ Même API = migration vers Kafka possible                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Composants de la Plateforme

### Stack Technique

| Couche | Composant | Rôle |
|--------|-----------|------|
| **Frontend** | React + TypeScript | UI DevOps multi-tenant |
| **Backend** | FastAPI (Python) | REST API, Kafka Producer |
| **Event Streaming** | Redpanda (Kafka API) | Hub de communication |
| **Automation** | AWX (Ansible) | Déploiement Gateway |
| **GitOps** | ArgoCD | Sync Kubernetes |
| **Identity** | Keycloak | SSO, RBAC, OIDC |
| **Secrets** | HashiCorp Vault | Rotation, PKI |
| **Observability** | OpenSearch | Logs, Traces, Analytics |
| **Monitoring** | Prometheus + Grafana | Métriques, Alerting |
| **Runtime** | webMethods Gateway | API Management |

### Infrastructure AWS

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS INFRASTRUCTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   VPC: 10.0.0.0/16                                              │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                                                          │   │
│   │   ┌─────────────────┐     ┌─────────────────┐           │   │
│   │   │  Public Subnet  │     │  Public Subnet  │           │   │
│   │   │   10.0.1.0/24   │     │   10.0.2.0/24   │           │   │
│   │   │                 │     │                 │           │   │
│   │   │   ┌─────────┐   │     │   ┌─────────┐   │           │   │
│   │   │   │   ALB   │   │     │   │   NAT   │   │           │   │
│   │   │   │         │   │     │   │ Gateway │   │           │   │
│   │   │   └─────────┘   │     │   └─────────┘   │           │   │
│   │   └─────────────────┘     └─────────────────┘           │   │
│   │                                                          │   │
│   │   ┌─────────────────┐     ┌─────────────────┐           │   │
│   │   │ Private Subnet  │     │ Private Subnet  │           │   │
│   │   │  10.0.10.0/24   │     │  10.0.20.0/24   │           │   │
│   │   │                 │     │                 │           │   │
│   │   │   ┌─────────────────────────────────┐   │           │   │
│   │   │   │         EKS CLUSTER             │   │           │   │
│   │   │   │                                 │   │           │   │
│   │   │   │  ┌───────┐ ┌───────┐ ┌───────┐  │   │           │   │
│   │   │   │  │Node 1 │ │Node 2 │ │Node 3 │  │   │           │   │
│   │   │   │  │t3.lrg │ │t3.lrg │ │t3.lrg │  │   │           │   │
│   │   │   │  └───────┘ └───────┘ └───────┘  │   │           │   │
│   │   │   │                                 │   │           │   │
│   │   │   └─────────────────────────────────┘   │           │   │
│   │   └─────────────────┘     └─────────────────┘           │   │
│   │                                                          │   │
│   │   ┌─────────────────────────────────────────────────┐   │   │
│   │   │              RDS PostgreSQL                      │   │   │
│   │   │              (Multi-AZ)                          │   │   │
│   │   └─────────────────────────────────────────────────┘   │   │
│   │                                                          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Sécurité

### Defense in Depth

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Layer 1: NETWORK                                               │
│   ─────────────────                                              │
│   • VPC isolé                                                    │
│   • Security Groups                                              │
│   • Private subnets pour workloads                              │
│   • TLS everywhere (cert-manager)                               │
│                                                                  │
│   Layer 2: IDENTITY                                              │
│   ─────────────────                                              │
│   • Keycloak (OIDC/SAML)                                        │
│   • JWT validation                                               │
│   • RBAC multi-tenant                                           │
│   • Session management                                          │
│                                                                  │
│   Layer 3: APPLICATION                                           │
│   ────────────────────                                           │
│   • Input validation                                             │
│   • CORS policy                                                  │
│   • Rate limiting                                                │
│   • Audit logging → Kafka                                       │
│                                                                  │
│   Layer 4: DATA                                                  │
│   ─────────────                                                  │
│   • Vault (secrets management)                                  │
│   • Encryption at rest (RDS, EBS)                               │
│   • Secret rotation (auto)                                      │
│   • Backup encryption                                           │
│                                                                  │
│   Layer 5: MONITORING                                            │
│   ───────────────────                                            │
│   • Security jobs (Phase 7)                                     │
│   • Certificate expiry alerts                                   │
│   • GitLab security scans                                       │
│   • Anomaly detection                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Kafka/Redpanda + AWX Automation | ✅ Complété |
| **Phase 2** | GitOps + Variables + IAM | 🔄 En cours |
| **Phase 3** | Vault + Gateway Alias | 📋 Planifié |
| **Phase 4** | OpenSearch + Monitoring | 📋 Planifié |
| **Phase 5** | Multi-environnements | 📋 Planifié |
| **Phase 6** | Demo Tenant + SSO + Docs | 📋 Planifié |
| **Phase 7** | Security Batch Jobs | 📋 Planifié |
| **Phase 8** | Developer Portal Custom (React) | 📋 Planifié |
| **Phase 9** | Ticketing (Demandes de Production) | 📋 Planifié |
| **Phase 10** | Resource Lifecycle (Tagging + Auto-Teardown) | 📋 Planifié |

---

## Phase 8 - Developer Portal Custom

**Objectif**: Développer un Developer Portal custom React, unifié avec le SSO Keycloak.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         DEVELOPER PORTAL - ARCHITECTURE                              │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                              DÉVELOPPEURS                                    │   │
│   │                                                                              │   │
│   │   • Découvrir les APIs disponibles                                          │   │
│   │   • Lire la documentation OpenAPI                                           │   │
│   │   • Créer des applications                                                   │   │
│   │   • Souscrire aux APIs                                                       │   │
│   │   • Tester les APIs (Try-It)                                                │   │
│   │   • Obtenir des code samples                                                │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                       │                                              │
│                                       ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                         DEVELOPER PORTAL (React)                             │   │
│   │                         https://portal.apim.cab-i.com                        │   │
│   │                                                                              │   │
│   │   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │   │
│   │   │ Catalogue  │ │  API Doc   │ │   Apps &   │ │  Try-It    │               │   │
│   │   │   APIs     │ │  Swagger   │ │   Subs     │ │  Console   │               │   │
│   │   └────────────┘ └────────────┘ └────────────┘ └────────────┘               │   │
│   └───────────────────────────────────┬─────────────────────────────────────────┘   │
│                                       │                                              │
│                                       │ /portal/* API                               │
│                                       ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                      CONTROL-PLANE API (FastAPI)                             │   │
│   │                                                                              │   │
│   │   ┌─────────────────────────────────────────────────────────────────────┐   │   │
│   │   │  /portal/apis         → Liste APIs publiées                         │   │   │
│   │   │  /portal/applications → CRUD Applications + credentials             │   │   │
│   │   │  /portal/subscriptions→ Gestion souscriptions                       │   │   │
│   │   │  /portal/try-it       → Proxy requêtes → Gateway                    │   │   │
│   │   └─────────────────────────────────────────────────────────────────────┘   │   │
│   │                                       │                                      │   │
│   │                          ┌────────────┴────────────┐                        │   │
│   │                          ▼                         ▼                        │   │
│   │                   ┌────────────┐            ┌────────────┐                  │   │
│   │                   │   Kafka    │            │   GitLab   │                  │   │
│   │                   │  (Events)  │            │  (GitOps)  │                  │   │
│   │                   │            │            │            │                  │   │
│   │                   │ app-created│            │ apps.yaml  │                  │   │
│   │                   │ sub-created│            │ subs.yaml  │                  │   │
│   │                   └────────────┘            └────────────┘                  │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Stack Technique

| Composant | Technologie |
|-----------|-------------|
| Frontend | React 18 + TypeScript + Vite |
| Styling | TailwindCSS |
| Auth | Keycloak OIDC |
| API Docs | Swagger-UI React |
| Code Editor | Monaco Editor |
| Backend | Control-Plane API (FastAPI) |

### Intégration Kafka

Le Developer Portal utilise Kafka pour les événements :

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Portal    │ ──▶ │   API       │ ──▶ │   Kafka     │
│   Action    │     │   Backend   │     │             │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
             ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
             │   GitLab    │            │   Gateway   │            │  OpenSearch │
             │  (GitOps)   │            │  (Runtime)  │            │   (Audit)   │
             │             │            │             │            │             │
             │ Sync apps   │            │ Create      │            │ Index       │
             │ & subs      │            │ API Keys    │            │ events      │
             └─────────────┘            └─────────────┘            └─────────────┘
```

**Topics Kafka utilisés** :
- `application-created` → Sync GitLab + provisionning Gateway
- `application-deleted` → Cleanup
- `subscription-created` → Activation API Key pour l'API
- `subscription-deleted` → Révocation
- `api-key-rotated` → Invalidation cache + audit

### Plan Détaillé

Voir [DEVELOPER-PORTAL-PLAN.md](DEVELOPER-PORTAL-PLAN.md) pour :
- Structure du projet
- Planning semaine par semaine
- Composants React détaillés
- Endpoints backend
- Configuration Keycloak

---

## Phase 9 - Ticketing (Demandes de Production)

**Objectif**: Workflow de validation manuelle pour les promotions STAGING → PROD avec règle anti-self-approval.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         TICKETING WORKFLOW                                           │
│                                                                                      │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐                      │
│   │  PENDING │───▶│ APPROVED │───▶│DEPLOYING │───▶│ DEPLOYED │                      │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘                      │
│        │                               │                                             │
│        ▼                               ▼                                             │
│   ┌──────────┐                   ┌──────────┐                                       │
│   │ REJECTED │                   │  FAILED  │                                       │
│   └──────────┘                   └──────────┘                                       │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Flux Event-Driven

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   DevOps    │────▶│   Git       │────▶│   Kafka     │
│   (Demande) │     │  (Commit)   │     │  (Event)    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                          ┌────────────────────┴────────────────────┐
                          │                                         │
                          ▼                                         ▼
                   ┌─────────────┐                           ┌─────────────┐
                   │   Email     │                           │   Slack     │
                   │   (CPI)     │                           │  (#prod)    │
                   └─────────────┘                           └─────────────┘
                          │
                          │ CPI approuve
                          ▼
                   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
                   │   API       │────▶│   Kafka     │────▶│    AWX      │
                   │  /approve   │     │  (Event)    │     │  (Deploy)   │
                   └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                  │
                                                                  │ Callback
                                                                  ▼
                   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
                   │   Git       │◀────│   API       │◀────│   AWX       │
                   │  (Update)   │     │ /callback   │     │  (Result)   │
                   └─────────────┘     └─────────────┘     └─────────────┘
```

### RBAC & Anti-Self-Approval

| Rôle | Créer | Approuver | Note |
|------|-------|-----------|------|
| DevOps | ✅ | ❌ | Crée pour son tenant |
| CPI Tenant | ✅ | ✅* | *Sauf ses propres demandes |
| CPI Admin | ✅ | ✅* | *Sauf ses propres demandes |

### Intégration Kafka

**Topics utilisés** :
- `promotion-requests` (topic principal)

**Events** :
- `request-created` → Notification CPI
- `request-approved` → Trigger AWX + notification demandeur
- `request-rejected` → Notification demandeur
- `deployment-succeeded` → Notification tous
- `deployment-failed` → Notification ops

### Plan Détaillé

Voir [TICKETING-SYSTEM-PLAN.md](TICKETING-SYSTEM-PLAN.md) pour :
- Format YAML des tickets
- Endpoints API complets
- Modèles Pydantic
- Composants React (RequestCard, Timeline, etc.)
- Templates email

---

## Phase 10 - Resource Lifecycle Management

**Objectif**: Tagging obligatoire et auto-suppression des ressources non-production pour optimiser les coûts.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      RESOURCE LIFECYCLE MANAGEMENT                                    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                         MANDATORY TAGS                                       │   │
│   │                                                                              │   │
│   │   environment    : dev | staging | sandbox | demo                           │   │
│   │   owner          : email du responsable                                     │   │
│   │   project        : nom du projet / tenant                                   │   │
│   │   cost-center    : code centre de coût                                      │   │
│   │   ttl            : durée de vie (7d, 14d, 30d max)                          │   │
│   │   created_at     : date de création (auto)                                  │   │
│   │   auto-teardown  : true | false                                             │   │
│   │   data-class     : public | internal | confidential | restricted            │   │
│   │                                                                              │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                         AUTO-TEARDOWN SCHEDULER                              │   │
│   │                                                                              │   │
│   │   EventBridge (cron: 0 2 * * *)                                             │   │
│   │        │                                                                     │   │
│   │        ▼                                                                     │   │
│   │   ┌──────────────┐                                                          │   │
│   │   │    Lambda    │                                                          │   │
│   │   │ cleanup-job  │                                                          │   │
│   │   └──────┬───────┘                                                          │   │
│   │          │                                                                   │   │
│   │    ┌─────┴─────────────────────────────────────────┐                        │   │
│   │    │                                               │                        │   │
│   │    ▼                                               ▼                        │   │
│   │  AWS Resources                              K8s Resources                   │   │
│   │  - EC2, RDS, S3                             - Namespaces, Pods              │   │
│   │                                                                              │   │
│   │   1. Query resources where auto-teardown=true                               │   │
│   │   2. Check if created_at + ttl < now()                                      │   │
│   │   3. Notify owner (48h → 24h → delete)                                      │   │
│   │   4. Delete expired resources                                               │   │
│   │   5. Audit log to Kafka + S3                                                │   │
│   │                                                                              │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Guardrails

| Règle | Description |
|-------|-------------|
| **Tag Validation** | Rejeter déploiement sans tags obligatoires |
| **TTL Maximum** | 30 jours max pour non-prod |
| **Data Protection** | `data-class=restricted` exclu de l'auto-teardown |
| **Owner Notification** | 48h → 24h → suppression |
| **Prod Exclusion** | `environment=prod` jamais supprimé automatiquement |

### Intégration Kafka

**Topics utilisés** :
- `resource-created` → Log création avec tags
- `resource-expiring` → Notification 48h/24h avant expiration
- `resource-deleted` → Audit trail suppression
- `tag-violation` → Alerte déploiement sans tags

### Implémentation

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Module Terraform | `common_tags` | Tags standardisés avec validations |
| Lambda | `resource-cleanup` | Suppression ressources expirées |
| EventBridge | Cron 2h UTC | Déclencheur quotidien |
| OPA Gatekeeper | K8s admission | Rejet pods sans tags |
| GitHub Actions | CI check | Validation tags avant merge |

---

## Gateway Admin Proxy (Phase 2.5)

### Architecture OIDC pour Administration Gateway

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 GATEWAY ADMIN PROXY - OIDC ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐                    ┌─────────────────────────────────┐    │
│   │   Client    │                    │      Control-Plane API          │    │
│   │  (UI/AWX)   │                    │  ┌─────────────────────────┐   │    │
│   │             │─── JWT Token ─────▶│  │  POST /v1/gateway/apis  │   │    │
│   │             │                    │  │                         │   │    │
│   └─────────────┘                    │  │  • Valide JWT (OIDC)    │   │    │
│                                      │  │  • Forward au Gateway   │   │    │
│                                      │  │  • Audit trail          │   │    │
│                                      │  └───────────┬─────────────┘   │    │
│                                      └──────────────┼─────────────────┘    │
│                                                     │                       │
│                                                     │ Forward request       │
│                                                     │ + JWT Token           │
│                                                     ▼                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      webMethods Gateway                              │   │
│   │  ┌─────────────────────────────────────────────────────────────┐    │   │
│   │  │  Gateway-Admin-API (Proxy vers port 5555)                   │    │   │
│   │  │                                                             │    │   │
│   │  │  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐   │    │   │
│   │  │  │ JWT Valid   │──▶│   Routing    │──▶│  Basic Auth    │   │    │   │
│   │  │  │ (Keycloak)  │   │  (Endpoint)  │   │  (Outbound)    │   │    │   │
│   │  │  └─────────────┘   └──────────────┘   └───────┬────────┘   │    │   │
│   │  └───────────────────────────────────────────────┼─────────────┘    │   │
│   │                                                  │                   │   │
│   │                                                  ▼                   │   │
│   │  ┌─────────────────────────────────────────────────────────────┐    │   │
│   │  │  Gateway Admin API (port 5555)                              │    │   │
│   │  │                                                             │    │   │
│   │  │  /rest/apigateway/apis                                      │    │   │
│   │  │  /rest/apigateway/applications                              │    │   │
│   │  │  /rest/apigateway/alias                                     │    │   │
│   │  │  ...                                                        │    │   │
│   │  └─────────────────────────────────────────────────────────────┘    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### OpenAPI 3.1.0 Compatibility

webMethods Gateway 10.15 ne supporte pas OpenAPI 3.1.0. Le playbook `deploy-api.yaml` convertit automatiquement :

```yaml
# Détection et conversion automatique
- name: Detect OpenAPI version and type
  set_fact:
    openapi_version: "{{ openapi_spec_content.json.openapi | default('2.0') }}"
    api_spec_type: "{{ 'swagger' if openapi_spec_content.json.swagger is defined else 'openapi' }}"

- name: Convert OpenAPI 3.1.x to 3.0.0 if needed
  set_fact:
    converted_spec: "{{ openapi_spec_content.json | combine({'openapi': '3.0.0'}) }}"
  when: openapi_version is version('3.1.0', '>=')
```

| Version OpenAPI | Support Gateway | Action |
|-----------------|-----------------|--------|
| Swagger 2.0 | ✅ Natif | Aucune conversion |
| OpenAPI 3.0.x | ✅ Natif | Aucune conversion |
| OpenAPI 3.1.x | ❌ Non supporté | Conversion → 3.0.0 |

---

## Conclusion

### Kafka comme Colonne Vertébrale

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   KAFKA N'EST PAS JUSTE UN MESSAGE BROKER                       │
│   ═══════════════════════════════════════                       │
│                                                                  │
│   C'est:                                                         │
│                                                                  │
│   🔗 Le SYSTÈME NERVEUX de la plateforme                        │
│      → Tous les composants communiquent via Kafka               │
│                                                                  │
│   📜 Le JOURNAL DE BORD immuable                                │
│      → Chaque action est tracée et auditable                    │
│                                                                  │
│   ⚡ Le DÉCOUPLEUR universel                                    │
│      → Services indépendants, évolutifs, résilients             │
│                                                                  │
│   🔄 Le REPLAY ENGINE                                           │
│      → Reconstruire l'état, debugger, analyser                  │
│                                                                  │
│   📊 La SOURCE DE VÉRITÉ pour les analytics                     │
│      → OpenSearch consomme, agrège, visualise                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Contact

| Rôle | Contact |
|------|---------|
| Architecture | architecture@cab-i.com |
| Platform Team | platform-team@cab-i.com |
| Security | security-team@cab-i.com |

---

*Document mis à jour le 23 Décembre 2024*
*APIM Platform v2 - CAB Ingénierie*
