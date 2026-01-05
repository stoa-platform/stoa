# STOA Platform v2 - Final Architecture

## Executive Summary

**STOA Platform v2** is a multi-tenant API management platform designed for enterprise, integrating best practices in DevOps, GitOps and Event-Driven Architecture.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              STOA PLATFORM v2                                            │
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

## Why Kafka? The Heart of the Architecture

### The Problem Without Kafka

```
                    SYNCHRONOUS ARCHITECTURE (Anti-Pattern)
                    ══════════════════════════════════════

    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
    │   UI    │────▶│   API   │────▶│   AWX   │────▶│ Gateway │
    └─────────┘     └─────────┘     └─────────┘     └─────────┘
         │               │               │               │
         │               │               │               │
         ▼               ▼               ▼               ▼
    ⏳ Waiting      ⏳ Blocked       ⏳ Timeout      ❌ Failure

    Problems:
    ❌ Tight coupling between services
    ❌ Cascading timeouts (API waits for AWX which waits for Gateway)
    ❌ No automatic retry
    ❌ Data loss if a service goes down
    ❌ Cannot scale independently
    ❌ A slow service blocks the entire pipeline
```

### The Solution With Kafka

```
                    EVENT-DRIVEN ARCHITECTURE (Best Practice)
                    ═══════════════════════════════════════════

    ┌─────────┐     ┌─────────┐     ┌─────────────────────────────────────┐
    │   UI    │────▶│   API   │────▶│              KAFKA                  │
    └─────────┘     └─────────┘     │                                     │
         │               │          │  ┌─────────────────────────────┐    │
         │          ✅ Immediate    │  │     TOPICS                  │    │
         │          return          │  │                             │    │
         ▼               │          │  │  api-created ──────────┐   │    │
    ✅ Instant          │          │  │  api-updated ──────────┤   │    │
    response             │          │  │  deploy-requests ──────┤   │    │
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

    Advantages:
    ✅ Complete service decoupling
    ✅ Immediate response to user
    ✅ Automatic retry (Kafka retention)
    ✅ No data loss (persistence)
    ✅ Horizontal scaling of each consumer
    ✅ Complete traceability (event sourcing)
```

---

## Kafka Topics - Detailed View

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

## Deployment Flow - Event-Driven

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
│  2. PROCESSING (Asynchronous)                                  │                        │
│  ════════════════════════════                                  │                        │
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

## Key Kafka Advantages

### 1. Decoupling & Resilience

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESILIENCE PATTERN                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   SCENARIO: AWX is unavailable for 2 hours                      │
│                                                                  │
│   WITHOUT KAFKA:                                                 │
│   ──────────────                                                 │
│   ❌ All deployments fail                                       │
│   ❌ Users see errors                                           │
│   ❌ Data lost, manual retry required                           │
│                                                                  │
│   WITH KAFKA:                                                    │
│   ───────────                                                    │
│   ✅ Events are stored in the topic                             │
│   ✅ API responds "accepted" immediately                        │
│   ✅ AWX returns → consumes all pending events                  │
│   ✅ No loss, no manual intervention                            │
│                                                                  │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐  │
│   │ Event 1 │     │ Event 2 │     │ Event 3 │     │ Event 4 │  │
│   │ 10:00   │     │ 10:15   │     │ 10:30   │     │ 10:45   │  │
│   └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘  │
│        │               │               │               │        │
│        └───────────────┴───────────────┴───────────────┘        │
│                              │                                   │
│                    Kafka Retention (7 days)                      │
│                              │                                   │
│                              ▼                                   │
│                     ┌───────────────┐                           │
│                     │  AWX returns  │                           │
│                     │  at 12:00     │                           │
│                     │               │                           │
│                     │  Processes    │                           │
│                     │  4 events     │                           │
│                     └───────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Horizontal Scalability

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
│   BEFORE (1 consumer)                                           │
│   ───────────────────                                           │
│        │           │           │           │           │        │
│        └───────────┴───────────┴───────────┴───────────┘        │
│                              │                                   │
│                    ┌─────────────────┐                          │
│                    │  AWX Worker 1   │  ← Overloaded!           │
│                    │  (all parts)    │                          │
│                    └─────────────────┘                          │
│                                                                  │
│   AFTER (3 consumers - Consumer Group)                          │
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
│   Result: 3x more throughput, automatically distributed         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Event Sourcing & Audit

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUDIT & COMPLIANCE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Topic: audit-log (retention: 1 year, compaction: key)         │
│                                                                  │
│   Each action is an immutable event:                            │
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
│   Advantages:                                                    │
│   ✅ Complete traceability (who, what, when)                    │
│   ✅ Replay possible (reconstruct state)                        │
│   ✅ Regulatory compliance (audit trail)                        │
│   ✅ Forensics in case of incident                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Multi-Consumer Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-CONSUMER PATTERN                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   A single "api-created" event triggers N parallel actions:     │
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
│  Deploys to K8s        Indexes for           Notifies team     │
│                        search                                   │
│                                                                  │
│   Each consumer group reads ALL the topic independently         │
│   → Adding a new consumer = 0 impact on others                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Redpanda vs Apache Kafka

```
┌─────────────────────────────────────────────────────────────────┐
│                    WHY REDPANDA?                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                                                          │   │
│   │   100% KAFKA API COMPATIBLE                              │   │
│   │   ══════════════════════════                             │   │
│   │                                                          │   │
│   │   • Same protocol, same clients                          │   │
│   │   • kafka-python, librdkafka work                        │   │
│   │   • Transparent migration                                │   │
│   │                                                          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌──────────────────────┬──────────────────────┐               │
│   │   Apache Kafka       │   Redpanda           │               │
│   ├──────────────────────┼──────────────────────┤               │
│   │   JVM (Java)         │   Native C++         │               │
│   │   ZooKeeper required*│   No ZooKeeper       │               │
│   │   3+ nodes min       │   1 node possible    │               │
│   │   ~2GB RAM min       │   ~500MB RAM         │               │
│   │   Complex config     │   Simple config      │               │
│   │   Latency ~10ms      │   Latency ~1ms       │               │
│   └──────────────────────┴──────────────────────┘               │
│   * KRaft mode available since Kafka 3.x                        │
│                                                                  │
│   FOR OUR CASE (EKS with limited resources):                    │
│   ──────────────────────────────────────────                    │
│   ✅ Redpanda = fewer resources                                 │
│   ✅ Redpanda = simplified deployment                           │
│   ✅ Redpanda Console included (admin UI)                       │
│   ✅ Same API = migration to Kafka possible                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Platform Components

### Technical Stack

| Layer | Component | Role |
|-------|-----------|------|
| **Frontend** | React + TypeScript | Multi-tenant DevOps UI |
| **Backend** | FastAPI (Python) | REST API, Kafka Producer |
| **Event Streaming** | Redpanda (Kafka API) | Communication Hub |
| **Automation** | AWX (Ansible) | Gateway Deployment |
| **GitOps** | ArgoCD | Kubernetes Sync |
| **Identity** | Keycloak | SSO, RBAC, OIDC |
| **Secrets** | HashiCorp Vault | Rotation, PKI |
| **Observability** | OpenSearch | Logs, Traces, Analytics |
| **Monitoring** | Prometheus + Grafana | Metrics, Alerting |
| **Runtime** | webMethods Gateway | API Management |

### AWS Infrastructure

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

## Security

### Defense in Depth

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Layer 1: NETWORK                                               │
│   ─────────────────                                              │
│   • Isolated VPC                                                 │
│   • Security Groups                                              │
│   • Private subnets for workloads                               │
│   • TLS everywhere (cert-manager)                               │
│                                                                  │
│   Layer 2: IDENTITY                                              │
│   ─────────────────                                              │
│   • Keycloak (OIDC/SAML)                                        │
│   • JWT validation                                               │
│   • Multi-tenant RBAC                                           │
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
│   • Automatic secret rotation                                   │
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
| **Phase 1** | Kafka/Redpanda + AWX Automation | ✅ Completed |
| **Phase 2** | GitOps + Variables + IAM | 🔄 In Progress |
| **Phase 3** | Vault + Gateway Alias | 📋 Planned |
| **Phase 4** | OpenSearch + Monitoring | 📋 Planned |
| **Phase 5** | Multi-environments | 📋 Planned |
| **Phase 6** | Demo Tenant + SSO + Docs | 📋 Planned |
| **Phase 7** | Security Batch Jobs | 📋 Planned |
| **Phase 8** | Custom Developer Portal (React) | 📋 Planned |
| **Phase 9** | Ticketing (Production Requests) | 📋 Planned |
| **Phase 10** | Resource Lifecycle (Tagging + Auto-Teardown) | 📋 Planned |

---

## Phase 8 - Custom Developer Portal

**Objective**: Develop a custom React Developer Portal, unified with Keycloak SSO.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         DEVELOPER PORTAL - ARCHITECTURE                              │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                              DEVELOPERS                                      │   │
│   │                                                                              │   │
│   │   • Discover available APIs                                                  │   │
│   │   • Read OpenAPI documentation                                               │   │
│   │   • Create applications                                                      │   │
│   │   • Subscribe to APIs                                                        │   │
│   │   • Test APIs (Try-It)                                                       │   │
│   │   • Get code samples                                                         │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                       │                                              │
│                                       ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                         DEVELOPER PORTAL (React)                             │   │
│   │                         https://portal.stoa.cab-i.com                        │   │
│   │                                                                              │   │
│   │   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │   │
│   │   │   API      │ │  API Doc   │ │   Apps &   │ │  Try-It    │               │   │
│   │   │  Catalog   │ │  Swagger   │ │   Subs     │ │  Console   │               │   │
│   │   └────────────┘ └────────────┘ └────────────┘ └────────────┘               │   │
│   └───────────────────────────────────┬─────────────────────────────────────────┘   │
│                                       │                                              │
│                                       │ /portal/* API                               │
│                                       ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                      CONTROL-PLANE API (FastAPI)                             │   │
│   │                                                                              │   │
│   │   ┌─────────────────────────────────────────────────────────────────────┐   │   │
│   │   │  /portal/apis         → List published APIs                         │   │   │
│   │   │  /portal/applications → CRUD Applications + credentials             │   │   │
│   │   │  /portal/subscriptions→ Subscription management                     │   │   │
│   │   │  /portal/try-it       → Proxy requests → Gateway                    │   │   │
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

### Technical Stack

| Component | Technology |
|-----------|------------|
| Frontend | React 18 + TypeScript + Vite |
| Styling | TailwindCSS |
| Auth | Keycloak OIDC |
| API Docs | Swagger-UI React |
| Code Editor | Monaco Editor |
| Backend | Control-Plane API (FastAPI) |

### Kafka Integration

The Developer Portal uses Kafka for events:

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

**Kafka Topics Used**:
- `application-created` → Sync GitLab + Gateway provisioning
- `application-deleted` → Cleanup
- `subscription-created` → API Key activation for the API
- `subscription-deleted` → Revocation
- `api-key-rotated` → Cache invalidation + audit

### Detailed Plan

See [DEVELOPER-PORTAL-PLAN.md](DEVELOPER-PORTAL-PLAN.md) for:
- Project structure
- Week-by-week planning
- Detailed React components
- Backend endpoints
- Keycloak configuration

---

## Phase 9 - Ticketing (Production Requests)

**Objective**: Manual validation workflow for STAGING → PROD promotions with anti-self-approval rule.

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

### Event-Driven Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   DevOps    │────▶│   Git       │────▶│   Kafka     │
│   (Request) │     │  (Commit)   │     │  (Event)    │
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
                          │ CPI approves
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

| Role | Create | Approve | Note |
|------|--------|---------|------|
| DevOps | ✅ | ❌ | Creates for their tenant |
| Tenant CPI | ✅ | ✅* | *Except their own requests |
| Admin CPI | ✅ | ✅* | *Except their own requests |

### Kafka Integration

**Topics Used**:
- `promotion-requests` (main topic)

**Events**:
- `request-created` → CPI Notification
- `request-approved` → Trigger AWX + requester notification
- `request-rejected` → Requester notification
- `deployment-succeeded` → Notify all
- `deployment-failed` → Ops notification

### Detailed Plan

See [TICKETING-SYSTEM-PLAN.md](TICKETING-SYSTEM-PLAN.md) for:
- Ticket YAML format
- Complete API endpoints
- Pydantic models
- React components (RequestCard, Timeline, etc.)
- Email templates

---

## Phase 10 - Resource Lifecycle Management

**Objective**: Mandatory tagging and auto-deletion of non-production resources to optimize costs.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      RESOURCE LIFECYCLE MANAGEMENT                                    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                         MANDATORY TAGS                                       │   │
│   │                                                                              │   │
│   │   environment    : dev | staging | sandbox | demo                           │   │
│   │   owner          : responsible's email                                      │   │
│   │   project        : project / tenant name                                    │   │
│   │   cost-center    : cost center code                                         │   │
│   │   ttl            : time-to-live (7d, 14d, 30d max)                          │   │
│   │   created_at     : creation date (auto)                                     │   │
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

| Rule | Description |
|------|-------------|
| **Tag Validation** | Reject deployment without mandatory tags |
| **Maximum TTL** | 30 days max for non-prod |
| **Data Protection** | `data-class=restricted` excluded from auto-teardown |
| **Owner Notification** | 48h → 24h → deletion |
| **Prod Exclusion** | `environment=prod` never automatically deleted |

### Kafka Integration

**Topics Used**:
- `resource-created` → Log creation with tags
- `resource-expiring` → Notification 48h/24h before expiration
- `resource-deleted` → Deletion audit trail
- `tag-violation` → Alert deployment without tags

### Implementation

| Component | Technology | Role |
|-----------|------------|------|
| Terraform Module | `common_tags` | Standardized tags with validations |
| Lambda | `resource-cleanup` | Delete expired resources |
| EventBridge | Cron 2h UTC | Daily trigger |
| OPA Gatekeeper | K8s admission | Reject pods without tags |
| GitHub Actions | CI check | Tag validation before merge |

---

## Gateway Admin Proxy (Phase 2.5)

### OIDC Architecture for Gateway Administration

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
│   └─────────────┘                    │  │  • Validates JWT (OIDC) │   │    │
│                                      │  │  • Forwards to Gateway  │   │    │
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
│   │  │  Gateway-Admin-API (Proxy to port 5555)                     │    │   │
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

webMethods Gateway 10.15 does not support OpenAPI 3.1.0. The `deploy-api.yaml` playbook automatically converts:

```yaml
# Automatic detection and conversion
- name: Detect OpenAPI version and type
  set_fact:
    openapi_version: "{{ openapi_spec_content.json.openapi | default('2.0') }}"
    api_spec_type: "{{ 'swagger' if openapi_spec_content.json.swagger is defined else 'openapi' }}"

- name: Convert OpenAPI 3.1.x to 3.0.0 if needed
  set_fact:
    converted_spec: "{{ openapi_spec_content.json | combine({'openapi': '3.0.0'}) }}"
  when: openapi_version is version('3.1.0', '>=')
```

| OpenAPI Version | Gateway Support | Action |
|-----------------|-----------------|--------|
| Swagger 2.0 | ✅ Native | No conversion |
| OpenAPI 3.0.x | ✅ Native | No conversion |
| OpenAPI 3.1.x | ❌ Not supported | Conversion → 3.0.0 |

---

## Conclusion

### Kafka as the Backbone

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   KAFKA IS NOT JUST A MESSAGE BROKER                            │
│   ══════════════════════════════════                            │
│                                                                  │
│   It is:                                                         │
│                                                                  │
│   🔗 The NERVOUS SYSTEM of the platform                         │
│      → All components communicate via Kafka                     │
│                                                                  │
│   📜 The immutable LOG BOOK                                     │
│      → Each action is traced and auditable                      │
│                                                                  │
│   ⚡ The universal DECOUPLER                                    │
│      → Independent, scalable, resilient services                │
│                                                                  │
│   🔄 The REPLAY ENGINE                                          │
│      → Reconstruct state, debug, analyze                        │
│                                                                  │
│   📊 The SOURCE OF TRUTH for analytics                          │
│      → OpenSearch consumes, aggregates, visualizes              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Contact

| Role | Contact |
|------|---------|
| Architecture | architecture@cab-i.com |
| Platform Team | platform-team@cab-i.com |
| Security | security-team@cab-i.com |

---

*Document updated on December 23, 2024*
*STOA Platform v2 - CAB Ingénierie*
