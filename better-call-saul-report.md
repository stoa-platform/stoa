# Better Call Saul - Audit Report

> **Philosophie:** "Suggérer sans promettre ce qui n'a jamais été vérifié."

**Generated:** 2026-01-26
**Script:** CAB-954 - STOA Legal Audit

---

## 🚨 1. Client Names to Anonymize

| Pattern | Found | Location | Replacement |
|---------|-------|----------|-------------|
| BDF | ⚠️ 1 | docs/CAPACITY-PLANNING.md:346 | "internal project" |

**Context:**
```
**Assumption:** ~8h/week available for STOA (excluding BDF)
```

**Fix:** Replace `BDF` with generic term or remove reference.

---

## ⚠️ 2. Dangerous Claims (Legal Risk)

### 2.1 Guarantees & Absolutes

| File | Line | Finding | Risk | Action |
|------|------|---------|------|--------|
| docs/runbooks/mcp-gateway-migration.md | 7 | "Zero-downtime migration" | Medium | Add "target" or "designed for" |
| CLA.md | 13, 126 | "certified" | Low | OK - DCO context (legal term) |

### 2.2 Superlatives & Comparisons

| File | Line | Finding | Risk | Action |
|------|------|---------|------|--------|
| - | - | None found | - | ✅ Clean |

### 2.3 False Client Claims

| File | Line | Finding | Risk | Action |
|------|------|---------|------|--------|
| CLA.md | 7, 127 | "Used by Linux, Kubernetes..." | Low | OK - Referencing DCO standard |
| CLAUDE.md | 140 | "used by Console UI" | Low | OK - Internal architecture doc |

### 2.4 Compliance Over-claims

| File | Line | Finding | Risk | Action |
|------|------|---------|------|--------|
| docs/ARCHITECTURE-COMPLETE.md | 1530 | "GDPR-compliant data handling" | High | Needs validation or soften to "designed for GDPR" |
| docs/TICKETING-SYSTEM-PLAN.md | 72, 379 | "PCI-DSS compliant payment flow" | High | This is example/template - OK if clearly labeled |
| README.md | 3189 | "PCI-DSS compliant payment flow" | High | Same - verify it's example code |

---

## 🔒 3. Security Claims (Need Team Coca Validation)

| File | Line | Finding | Risk | Action |
|------|------|---------|------|--------|
| docs/TECHNOLOGY-CHOICES.md | 77 | "battle-tested" | Medium | Referring to PostgreSQL (30+ years) - OK |

**Verdict:** Only 1 security claim found, referring to PostgreSQL maturity. ✅ Acceptable.

---

## 💰 4. Pricing Mentions (Check Consistency)

### AWS Infrastructure Costs (README.md)

| Resource | Cost | Status |
|----------|------|--------|
| EKS Cluster | ~$72 | ✅ |
| EC2 (3x t3.large) | ~$180 | ✅ |
| RDS PostgreSQL | ~$25 | ✅ |
| ALB | ~$20 | ✅ |
| OpenSearch | ~$35 | ✅ |
| ECR | ~$5 | ✅ |
| Route 53 | ~$1 | ✅ |
| Secrets Manager | ~$2 | ✅ |
| Bandwidth | ~$10 | ✅ |
| **TOTAL** | **~$350/mois** | ✅ |

### Technology Comparisons

| File | Line | Context |
|------|------|---------|
| docs/TECHNOLOGY-CHOICES.md | 93 | Keycloak: Free vs Auth0: ~$23/1K MAU vs Okta: ~$2/user/mo |
| docs/TECHNOLOGY-CHOICES.md | 120 | ELK: Free vs Datadog: ~$15-30/host/mo |

### Contract Templates

| File | Context |
|------|---------|
| stoa-catalog/_templates/enterprise.yaml | Enterprise tier limits (internal config) |
| stoa-catalog/_templates/starter.yaml | Starter tier limits (internal config) |

### Legal Document

| File | Line | Finding |
|------|------|---------|
| legal/DESIGN_PARTNER_AGREEMENT_ENTERPRISE_EN.md | 232 | Liability cap: **€5,000** |

**Verdict:** Pricing is internal cost estimates or technology comparisons. No public-facing pricing promises found. ✅

---

## 🔗 5. STOA URLs to Verify

### Production URLs (gostoa.dev)

| Subdomain | Purpose | Status |
|-----------|---------|--------|
| console.gostoa.dev | Console UI | 🔍 Verify |
| portal.gostoa.dev | Developer Portal | 🔍 Verify |
| api.gostoa.dev | Control Plane API | 🔍 Verify |
| apis.gostoa.dev | Gateway Runtime | 🔍 Verify |
| auth.gostoa.dev | Keycloak | 🔍 Verify |
| gateway.gostoa.dev | Gateway Admin | 🔍 Verify |
| mcp.gostoa.dev | MCP Gateway | 🔍 Verify |
| awx.gostoa.dev | AWX | 🔍 Verify |
| argocd.gostoa.dev | ArgoCD | 🔍 Verify |
| vault.gostoa.dev | Vault | 🔍 Verify |
| grafana.gostoa.dev | Grafana | 🔍 Verify |
| prometheus.gostoa.dev | Prometheus | 🔍 Verify |
| loki.gostoa.dev | Loki | 🔍 Verify |
| jenkins.gostoa.dev | Jenkins | 🔍 Verify |
| opensearch.gostoa.dev | OpenSearch | 🔍 Verify |
| docs.gostoa.dev | Documentation | 🔍 Verify |
| gitlab.gostoa.dev | GitLab | 🔍 Verify |

### Staging URLs

All `*.staging.gostoa.dev` URLs found - internal use only.

---

## ✅ Recommended Actions

| Priority | Issue | File | Action |
|----------|-------|------|--------|
| **P0** | BDF client reference | docs/CAPACITY-PLANNING.md:346 | Remove or anonymize |
| **P1** | Zero-downtime claim | docs/runbooks/mcp-gateway-migration.md:7 | Soften to "designed for zero-downtime" |
| **P1** | GDPR-compliant claim | docs/ARCHITECTURE-COMPLETE.md:1530 | Validate or soften to "designed for GDPR compliance" |
| **P2** | PCI-DSS claims in examples | README.md, TICKETING-SYSTEM-PLAN.md | Ensure clearly marked as examples |
| **P2** | Verify production URLs | All *.gostoa.dev | Test accessibility |

---

## Summary

| Category | Findings | Risk Level |
|----------|----------|------------|
| 🚨 Client Names | 1 (BDF) | Medium |
| ⚠️ Dangerous Claims | 4 | Low-Medium |
| 🔒 Security Claims | 1 (battle-tested PostgreSQL) | Low |
| 💰 Pricing | Internal only | Low |
| 🔗 URLs | 17 subdomains to verify | Low |

**Overall Assessment:** The codebase is relatively clean. Main actions:
1. Remove the `BDF` reference
2. Soften the `Zero-downtime` and `GDPR-compliant` claims
3. Verify all production URLs are accessible

---

*Generated by Better Call Saul Audit (CAB-954)*
