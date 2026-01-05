# STOA Platform - Capacity Planning Q1-Q3 2026

**Date:** 05/01/2026
**Version:** 4.0 (post Phase 9.5 completion)
**Target:** Release v1.0 - July 31, 2026

---

## Summary

| Quarter | Milestone | Estimated Days | Remaining Days | Progress |
|---------|-----------|----------------|----------------|----------|
| **Q1** | Foundations (Logos) | 8d | **4.5d** | 44% |
| **Q2** | Stability (Apatheia) | 10d | **5d** | 50% |
| **Q3** | Release v1.0 | 9d | 9d | 0% |
| **TOTAL** | | **27d** | **18.5d** | **31%** |

---

## Completed Phases ✅

### Phase 1 - Event-Driven Architecture ✅
- [x] CAB-211: [Phase 1] Event-Driven Architecture (Epic)
- [x] CAB-212: APIM-101: Redpanda Kafka Cluster
- [x] CAB-213: APIM-102: AWX Ansible Tower Deployment
- [x] CAB-214: APIM-103: Control-Plane API (FastAPI)
- [x] CAB-215: APIM-104: Control-Plane UI (React)
**5/5 issues** ✅

### Phase 2 - GitOps + ArgoCD ✅
- [x] CAB-216: [Phase 2] GitOps + ArgoCD (Epic)
- [x] CAB-217: APIM-201: GitOps Templates Structure
- [x] CAB-218: APIM-202: Variable Resolver Service
- [x] CAB-219: APIM-203: IAM Sync Service (Git → Keycloak)
- [x] CAB-220: APIM-204: ArgoCD Deployment
- [x] CAB-221: APIM-205: GitLab stoa-gitops Repository
**6/6 issues** ✅

### Phase 2.5 - Validation E2E ✅
- [x] CAB-222: [Phase 2.5] Validation E2E (Epic)
- [x] CAB-223: APIM-251: Gateway OIDC Configuration
- [x] CAB-224: APIM-252: Gateway Admin Service (Proxy OIDC)
- [x] CAB-225: APIM-253: Playbooks Ansible E2E
- [x] CAB-226: APIM-254: Secrets AWS Secrets Manager
**5/5 issues** ✅

### Phase 3 - Vault + Secrets ✅
- [x] CAB-6: [Phase 3] Vault + Alias - Finalization (Epic)
- [x] CAB-133: APIM-301: Deploy Vault on EKS
- [x] CAB-134: APIM-302: Configure Kubernetes Vault Auth
- [x] CAB-135: APIM-303: Secrets structure per tenant
- [x] CAB-136: APIM-304: Control Plane → Vault Integration
- [x] CAB-137: APIM-305: Automatic credential rotation
**6/6 issues** ✅

### Phase 12 - MCP Gateway ✅
- [x] CAB-119: [Phase 12] STOA Gateway + Copilot (Epic)
- [x] CAB-120: MCP-1201: Gateway Core + Keycloak Auth
- [x] CAB-199: MCP-1201b: Gateway Tests & Tools
- [x] CAB-121: MCP-1202: Tool Registry Kubernetes CRDs
- [x] CAB-122: MCP-1203: OPA Policy Engine Integration
- [x] CAB-123: MCP-1204: Metering Pipeline (Kafka + ksqlDB)
- [x] CAB-124: MCP-1205: Portal Integration - Tool Catalog
**7/7 issues** ✅

### Phase 9.5 - Production Readiness ✅ 🆕
- [x] CAB-103: Phase 9.5: Production Readiness (Epic)
- [x] CAB-104: APIM-9501: Backup/Restore AWX
- [x] CAB-105: APIM-9502: Backup/Restore Vault
- [x] CAB-106: APIM-9503: Load Test Pipeline (K6)
- [x] CAB-107: APIM-9504: Operational Runbooks
- [x] CAB-108: APIM-9505: Security Audit (OWASP ZAP)
- [x] CAB-109: APIM-9506: Chaos Testing (LitmusChaos)
- [x] CAB-110: APIM-9507: SLO/SLA Definition
- [x] CAB-187: [Docs] Internationalization - Switch to English
- [x] CAB-236: APIM-9508: Penetration Testing
**10/10 issues** ✅

### Infrastructure - Rebranding ✅
- [x] CAB-196: [Infra] Rebranding APIM → STOA
- [x] CAB-197: [Infra] DNS/TLS Migration to *.stoa.cab-i.com
- [x] CAB-198: [Infra] Centralized BASE_DOMAIN configuration
**3/3 issues** ✅

---

## Q1 2026 - Foundations (Logos)
**Deadline:** March 31, 2026 | **Linear:** CAB-171

### Remaining Issues by Phase

| Phase | Scope | Est. | Issues | Status |
|-------|-------|------|--------|--------|
| ~~**3**~~ | ~~Vault + Secrets~~ | ~~1.5d~~ | ~~CAB-6 + 5 sub~~ | ✅ Done |
| ~~**12**~~ | ~~MCP Gateway~~ | ~~2d~~ | ~~CAB-119 + 6 sub~~ | ✅ Done |
| **2.6** | Cilium Foundation | 1.25d | CAB-126 (epic) + 6 sub | Backlog |
| **14** | GTM Strategy (01-03) | 1d | CAB-201, 202, 203 | Backlog |
| **4** | OpenSearch + Monitoring | 1.25d | CAB-2 (epic) + 4 sub | Backlog |
| **5** | Multi-env STAGING | 1d | CAB-3 (epic) + 3 sub | Backlog |

### Phase 2.6 - Cilium Foundation
- [ ] CAB-126: [Phase 2.6] Cilium Network Foundation (Epic)
- [ ] CAB-127: APIM-261: Install Cilium on EKS
- [ ] CAB-128: APIM-262: Gateway API CRDs + GatewayClass
- [ ] CAB-129: APIM-263: Migrate Nginx Ingress → Gateway API
- [ ] CAB-130: APIM-264: CiliumNetworkPolicy - Default deny
- [ ] CAB-131: APIM-265: Hubble - Network Observability
- [ ] CAB-132: APIM-266: Cilium Migration Documentation

### Phase 14 - GTM Q1 (Strategy)
- [ ] CAB-201: GTM-01: Open Core Strategy documented
- [ ] CAB-202: GTM-02: Licensing choice (Apache 2.0 vs dual)
- [ ] CAB-203: GTM-03: Repository structure (mono vs multi-repo)

### Phase 4 - OpenSearch + Monitoring
- [ ] CAB-2: [Phase 4] OpenSearch + Monitoring (Epic)
- [ ] CAB-9: APIM-401: Deploy Amazon OpenSearch on EKS
- [ ] CAB-10: APIM-402: Configure FluentBit for log shipping
- [ ] CAB-11: APIM-403: Deploy Prometheus + Grafana
- [ ] CAB-12: APIM-404: Create OpenSearch dashboards

### Phase 5 - Multi-environment
- [ ] CAB-3: [Phase 5] Multi-environment (Epic)
- [ ] CAB-13: APIM-501: Create STAGING environment
- [ ] CAB-14: APIM-502: Playbook promote-environment.yaml
- [ ] CAB-15: APIM-503: AWX Job Template Promote API

### Q1 Metrics
- **Total issues:** 31
- **Done:** 13 (42%)
- **Remaining:** 18

---

## Q2 2026 - Stability (Apatheia)
**Deadline:** June 30, 2026 | **Linear:** CAB-172

### Issues by Phase

| Phase | Scope | Est. | Issues | Status |
|-------|-------|------|--------|--------|
| **8** | Portal Self-Service | 2d | CAB-5 (epic) + 6 sub | Backlog |
| **9** | Ticketing ITSM | 2d | CAB-4 (epic) + 8 sub | Backlog |
| **7** | Security Jobs | 1.25d | CAB-8 (epic) + 5 sub | Backlog |
| ~~**9.5**~~ | ~~Production Readiness~~ | ~~2.5d~~ | ~~CAB-103 + 9 sub~~ | ✅ **Done** |
| **6** | Demo Tenant | 0.75d | CAB-7 (epic) + 4 sub | Backlog |
| **14** | GTM Docs + Site (04-07) | 1.5d | CAB-204→208 | Backlog |

### Phase 8 - Portal Self-Service
- [ ] CAB-5: [Phase 8] Portal Self-Service (Epic)
- [ ] CAB-26: APIM-801: Setup Developer Portal project
- [ ] CAB-145: APIM-802: Browsable API Catalog
- [ ] CAB-146: APIM-803: Applications and subscriptions management
- [ ] CAB-147: APIM-804: Developer consumption dashboard
- [ ] CAB-148: APIM-805: Guided onboarding for new developers
- [ ] CAB-188: [Portal] Setup i18n infrastructure

### Phase 9 - Ticketing ITSM
- [ ] CAB-4: [Phase 9] Ticketing ITSM (Epic)
- [ ] CAB-16: APIM-901: PromotionRequest Model + Git Service
- [ ] CAB-17: APIM-902: API Endpoints /v1/requests/prod
- [ ] CAB-18: APIM-903: Approve/Reject Workflow
- [ ] CAB-19: APIM-904: AWX callback webhook
- [ ] CAB-20: APIM-905: UI - Request list page
- [ ] CAB-21: APIM-906: UI - New request form
- [ ] CAB-22: APIM-907: UI - Detail page + Approve/Reject
- [ ] CAB-23: APIM-908: Kafka Events + Notifications

### Phase 7 - Security Jobs
- [ ] CAB-8: [Phase 7] Security Jobs (Epic)
- [ ] CAB-25: APIM-701: Docker image apim-security-jobs
- [ ] CAB-141: APIM-702: Image vulnerability scan (Trivy)
- [ ] CAB-142: APIM-703: Secrets detection in code (Gitleaks)
- [ ] CAB-143: APIM-704: TLS certificate expiration monitoring
- [ ] CAB-144: APIM-705: CIS Benchmark compliance checks

### Phase 6 - Demo Tenant
- [ ] CAB-7: [Phase 6] Demo Tenant (Epic)
- [ ] CAB-24: APIM-601: Create demo tenant with beta users
- [ ] CAB-138: APIM-602: Deploy demo APIs
- [ ] CAB-139: APIM-603: Document demo scenarios
- [ ] CAB-140: APIM-604: Automatic demo tenant reset

### Phase 14 - GTM Q2 (Docs + Site)
- [ ] CAB-204: GTM-04: Public documentation (Docusaurus)
- [ ] CAB-205: GTM-05: STOA Landing page
- [ ] CAB-206: GTM-06: Community channels (Discord, GitHub)
- [ ] CAB-207: GTM-07: Public roadmap
- [ ] CAB-208: GTM-08: IBM Partnership positioning

### Q2 Metrics
- **Total issues:** 41
- **Done:** 10 (24%) ← Phase 9.5 moved to Done
- **Remaining:** 31

---

## Q3 2026 - Release v1.0 (Oikeiosis + Ataraxia)
**Deadline:** July 31, 2026 | **Linear:** CAB-173

### Issues by Phase

| Phase | Scope | Est. | Issues | Status |
|-------|-------|------|--------|--------|
| **10** | Resource Lifecycle | 3d | CAB-27 (epic) + 10 sub | Backlog |
| **4.5** | Jenkins Orchestration | 3d | CAB-92 (epic) + 10 sub | Backlog |
| **14** | GTM Launch (08-10) | 1d | CAB-209, 210 | Backlog |
| **11** | Resource Advanced (bonus) | 2d | CAB-82 (epic) + 8 sub | Backlog |

### Phase 10 - Resource Lifecycle Management
- [ ] CAB-27: [Phase 10] Resource Lifecycle Management (Epic)
- [ ] CAB-28: APIM-1001: Terraform common_tags Module
- [ ] CAB-29: APIM-1002: Lambda Resource Cleanup
- [ ] CAB-30: APIM-1003: EventBridge Schedule
- [ ] CAB-31: APIM-1004: Owner Expiration Notifications
- [ ] CAB-32: APIM-1005: OPA Gatekeeper Policies
- [ ] CAB-33: APIM-1006: GitHub Actions Tag Governance
- [ ] CAB-34: APIM-1007: Kafka Events Resource Lifecycle
- [ ] CAB-35: APIM-1008: Grafana Dashboard Resource Lifecycle
- [ ] CAB-36: APIM-1009: n8n Multi-Cloud Workflow (optional)
- [ ] CAB-37: APIM-1010: Tagging Policy Documentation

### Phase 4.5 - Jenkins Orchestration Layer
- [ ] CAB-92: [Phase 4.5] Jenkins Orchestration Layer (Epic)
- [ ] CAB-93: [Jenkins] Deploy Jenkins on EKS with JCasC
- [ ] CAB-94: [Jenkins] Keycloak OIDC Integration for SSO
- [ ] CAB-95: [Jenkins] Kafka Consumer Service → Jenkins Job Trigger
- [ ] CAB-96: [Jenkins] Deploy API Pipeline with Approval Gates
- [ ] CAB-97: [Jenkins] Rollback API Pipeline
- [ ] CAB-98: [Jenkins] Shared Library reusable functions
- [ ] CAB-99: [Jenkins] AWX Job Trigger Integration
- [ ] CAB-100: [Jenkins] Prometheus Metrics and Grafana Dashboard
- [ ] CAB-101: [Jenkins] Sync Gateway Configuration Pipeline
- [ ] CAB-102: [Jenkins] Blue Ocean UI and job organization

### Phase 14 - GTM Q3 (Launch)
- [ ] CAB-209: GTM-09: Pricing tiers definition
- [ ] CAB-210: GTM-10: Beta program structure

### Phase 11 - Resource Lifecycle Advanced (Bonus)
- [ ] CAB-82: [Phase 11] Resource Lifecycle Advanced (Epic)
- [ ] CAB-83: [Terraform] Quotas per project/tenant
- [ ] CAB-84: [Config] Whitelist never-delete resources
- [ ] CAB-85: [Lambda] Ordered destruction with dependencies
- [ ] CAB-86: [API] Self-service TTL Extension endpoint
- [ ] CAB-87: [Lambda] Snooze buttons in emails
- [ ] CAB-88: [Lambda] Avoided cost calculator
- [ ] CAB-89: [Grafana] Cost Savings Dashboard
- [ ] CAB-90: [n8n] Complete workflow with Notion
- [ ] CAB-91: [Lambda] Hourly cron pre-alerts

### Q3 Metrics
- **Total issues:** 33
- **Done:** 0 (0%)
- **Remaining:** 33

---

## Issue Overview

| Status | Count | % |
|--------|-------|---|
| **Done** | **42** | **40%** |
| Backlog | 63 | 60% |
| **TOTAL** | **105** | 100% |

### Completed Issues (42)

#### Phase 1 - Event-Driven (5)
1. CAB-211: [Phase 1] Event-Driven Architecture
2. CAB-212: APIM-101: Redpanda Kafka Cluster
3. CAB-213: APIM-102: AWX Ansible Tower Deployment
4. CAB-214: APIM-103: Control-Plane API (FastAPI)
5. CAB-215: APIM-104: Control-Plane UI (React)

#### Phase 2 - GitOps (6)
6. CAB-216: [Phase 2] GitOps + ArgoCD
7. CAB-217: APIM-201: GitOps Templates Structure
8. CAB-218: APIM-202: Variable Resolver Service
9. CAB-219: APIM-203: IAM Sync Service
10. CAB-220: APIM-204: ArgoCD Deployment
11. CAB-221: APIM-205: GitLab stoa-gitops Repository

#### Phase 2.5 - Validation (5)
12. CAB-222: [Phase 2.5] Validation E2E
13. CAB-223: APIM-251: Gateway OIDC Configuration
14. CAB-224: APIM-252: Gateway Admin Service
15. CAB-225: APIM-253: Playbooks Ansible E2E
16. CAB-226: APIM-254: Secrets AWS Secrets Manager

#### Phase 3 - Vault (6)
17. CAB-6: [Phase 3] Vault + Alias
18. CAB-133: APIM-301: Deploy Vault on EKS
19. CAB-134: APIM-302: Kubernetes Vault Auth
20. CAB-135: APIM-303: Secrets structure per tenant
21. CAB-136: APIM-304: Control Plane → Vault Integration
22. CAB-137: APIM-305: Automatic credential rotation

#### Phase 12 - MCP Gateway (7)
23. CAB-119: [Phase 12] STOA Gateway + Copilot
24. CAB-120: MCP-1201: Gateway Core + Keycloak Auth
25. CAB-199: MCP-1201b: Gateway Tests & Tools
26. CAB-121: MCP-1202: Tool Registry Kubernetes CRDs
27. CAB-122: MCP-1203: OPA Policy Engine Integration
28. CAB-123: MCP-1204: Metering Pipeline
29. CAB-124: MCP-1205: Portal Integration - Tool Catalog

#### Phase 9.5 - Production Readiness (10)
30. CAB-103: Phase 9.5: Production Readiness
31. CAB-104: APIM-9501: Backup/Restore AWX
32. CAB-105: APIM-9502: Backup/Restore Vault
33. CAB-106: APIM-9503: Load Test Pipeline (K6)
34. CAB-107: APIM-9504: Operational Runbooks
35. CAB-108: APIM-9505: Security Audit (OWASP)
36. CAB-109: APIM-9506: Chaos Testing
37. CAB-110: APIM-9507: SLO/SLA Definition
38. CAB-187: [Docs] Internationalization EN
39. CAB-236: APIM-9508: Penetration Testing

#### Infrastructure (3)
40. CAB-196: [Infra] Rebranding APIM → STOA
41. CAB-197: [Infra] DNS/TLS Migration
42. CAB-198: [Infra] BASE_DOMAIN configuration

---

## Priority Next Actions

### Immediate (Cycle 2: Jan 5-11)
1. **CAB-238** - E2E Testing Framework (In Progress)
2. **CAB-246** - Bootstrap Developer Portal UI
3. **CAB-247** - MCP Subscription API Backend

### Short term (January 2026)
1. Phase 2.6 - Cilium Foundation (CAB-126 epic)
2. Phase 14 GTM - Open Core Strategy docs (CAB-201, 202, 203)

### Medium term (February-March 2026)
1. Phase 4 - OpenSearch + Monitoring
2. Phase 5 - Multi-env STAGING

---

## Estimated Availability

**Assumption:** ~8h/week available for STOA (excluding BDF)

| Month | Weeks | Available Hours | Day Equivalent |
|-------|-------|-----------------|----------------|
| January | 4 | 32h | 4d |
| February | 4 | 32h | 4d |
| March | 4 | 32h | 4d |
| **Q1 Total** | 12 | 96h | **12d** |
| April | 4 | 32h | 4d |
| May | 4 | 32h | 4d |
| June | 4 | 32h | 4d |
| **Q2 Total** | 12 | 96h | **12d** |
| July | 4 | 32h | 4d |
| **Q3 (partial)** | 4 | 32h | **4d** |

**Total Q1-Q3 Capacity:** ~28d → **Remaining Estimate: 18.5d** ✅ Achievable

---

## Velocity Metrics (observed)

| Metric | Before Claude | With Claude | Boost |
|--------|---------------|-------------|-------|
| Issue average | 2-4 days | 2-4 hours | **x4-x8** |
| Phase 12 (6 issues) | ~10 days | ~10 hours | **x8** |
| Phase 9.5 (10 issues) | ~15 days | ~6 hours | **x20** |
| Tests generated | ~30/day | 118 in 4h | **x10** |

---

*Generated on 05/01/2026 - Based on 105 Linear issues*
*42 Done (40%) | 63 Backlog (60%)*
