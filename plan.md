# Plan: Demo Design Partner (24 fev 2026)

> **Last updated:** 2026-02-11 (CAB-1133 Portal tests merged — PR #308)
> **Status:** Phase 1+2 DONE — 5/5 livrables. OVH + Hetzner: ✅ COMPLETE. Portal tests: 427 (PR #308)
> **Next action:** Dry-runs (Phase 4), Demo Day 24 fev
> **Full plan:** [stoa-strategy/execution/plan-demo-partner.md](private repo)

---

## Executive Summary

**Mission:** Prepare 5-min "Design Partner" presentation for enterprise prospect (DSI + senior architects)
**Deadline:** Vendredi 14 fev EOD (urgent track), 24 fev (demo day)
**Livrables:** Email + Script verbal 5min + Slides presentation + Staging guide + MOU draft — ALL DONE

---

## Livrables Prioritaires

| # | Livrable | Deadline | Status |
|---|----------|----------|--------|
| 1 | Script verbal 5min | 14 fev | ✅ DONE |
| 2 | Slides presentation (6+4 backup) | 14 fev | ✅ DONE |
| 3 | Email design partner contact | 14 fev EOD | ✅ DONE (ready to send) |
| 4 | Staging preview guide | 16 fev | ✅ DONE |
| 5 | MOU draft 2 pages | 21 fev | ✅ DONE |
| 6 | Dry-run 3x | 23 fev | PENDING |

---

## Execution Phases

| Phase | Timeline | Deliverables | Status |
|-------|----------|--------------|--------|
| Phase 1 | 10 fev | Email + Script + Slides | DONE |
| Phase 2 | 10 fev | Staging + MOU | DONE |
| Phase 3 | 14-17 fev | Feedback loop (send email, collect feedback) | PENDING |
| Phase 4 | 18-23 fev | Dry-runs 3x (Human + Claude adjustments) | PENDING |
| Phase 5 | 24 fev | Demo Day | PENDING |

---

## Ship/Show/Ask

**Mode:** Ship (all deliverables — internal docs, zero risk, zero code change)
**Confidence:** [High] — detailed context, binary DoD per deliverable

---

## Security Note

Sensitive details (client identity, contact names, pricing, internal strategy) are in the
private `stoa-strategy` repository. This file contains only the execution structure.

---

## OVH Production Migration (11 fev 2026)

| Phase | Status |
|-------|--------|
| Phase 0: OVH Manager (cluster + DB + PAT) | ✅ DONE |
| Phase 1: Bootstrap (nginx-ingress, cert-manager) | ✅ DONE |
| Phase 2: Deploy (6 apps, 9 pods, K8s secrets) | ✅ DONE |
| Phase 3: DNS Switch (prod→OVH, staging→Hetzner) | ✅ DONE |
| Phase 4: CI/CD (KUBECONFIG_B64 secret) | ✅ DONE |
| Phase 5: Verify (12/12 endpoints HTTPS OK) | ✅ DONE |

**Architecture:** OVH MKS GRA9 (3x B2-15) + Managed PostgreSQL 16 + K8s Secrets
**LB IP:** `5.196.236.53` (prod) / `46.225.38.168` (staging)
**Cost:** ~€135/mois OVH + ~€45/mois Hetzner staging = ~€180/mois total
**Vault/ESO:** deferred (manifests ready at `~/ovh-production/k8s/vault/` + `eso/`)

---

## Hetzner Staging — K3s Standalone Migration (11 fev 2026)

**Goal:** Passer de K3s HA (2 masters + 2 workers) a K3s standalone (1 server + 3 agents) pour liberer de la capacite et pouvoir deployer l'observability stack sur 5 serveurs.

**Architecture:**
| Serveur | IP | Hostname | Role |
|---------|-----|----------|------|
| server | 46.225.112.68 | stoa-staging-server | K3s standalone (control-plane + worker) |
| agent-1 | 159.69.109.5 | stoa-staging-agent-1 | K3s agent |
| agent-2 | 167.235.22.166 | stoa-staging-agent-2 | K3s agent |
| agent-3 | 46.225.103.50 | stoa-staging-agent-3 | K3s agent |
| postgres | 46.225.118.41 | — | PostgreSQL 16 |

**Capacite:** 4 nodes K8s (16 vCPU, 32 GB) — suffisant pour 6 core apps + Prometheus + Grafana + OpenSearch

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Backup (pg_dump, manifests, kubeconfig) | ✅ DONE |
| Phase 1 | Teardown K3s HA (uninstall sur 4 nodes) | ✅ DONE |
| Phase 2 | Install K3s standalone sur server (SQLite) | ✅ DONE |
| Phase 3 | Join 3 agents (staging names) | ✅ DONE |
| Phase 4 | Redeploy apps (secrets, configmaps, 6 apps, staging ingress) | ✅ DONE |
| Phase 5 | Verify (6/6 pods Ready, 6 TLS certs, 6/6 HTTPS OK) | ✅ DONE |
| Phase 6 | Prometheus + Grafana (Helm kube-prometheus-stack) | ✅ DONE |
| Phase 7 | DNS records staging-grafana/prometheus (Cloudflare) | PENDING |
| Phase 8 | OpenSearch (optional) | DEFERRED |

---

## Archive: Cycle 7 Scoreboard

> Cycle 7 complete: 225 pts / 22 PRs (9-10 fev 2026)
> Demo Sprint D1-D11 complete + R1 MCP endpoints
> Native Observability: PRs #299 (Platform Metrics) + #300 (Request Explorer) — replaced iframe embeds with native React dashboards querying Prometheus. 68 tests, coverage >50%.
> Docker-compose: PR #301 — Console local build + Grafana OIDC auto-login + nginx Prometheus proxy
> Total PRs this session: #299, #300, #301 (3 PRs, ~700 LOC new code + 68 tests)
> Remaining: CAB-1035 (2 pts manual), CAB-1066 (34 pts stoa-web, stretch)
> CAB-1133 Portal Test Suite: PR #308 merged (164 new tests, 13 pages × 4 personas, 427 total)
