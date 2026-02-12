# Content Expansion — Compliance Checklist (2026-02-11)

## Overview

As STOA expands content to reach freelancers, SMBs, and security practitioners, new content must follow `content-compliance.md` rigorously. This checklist ensures all new pieces avoid P0/P1 violations.

---

## Pre-Publication Checklist (Every Content Piece)

### 1. Competitor Mentions

- [ ] **No competitor pricing claims?**
  - ❌ "Kong charges $0.60 per 1K API calls"
  - ❌ "MuleSoft licenses cost $X/year"
  - ✅ "Kong offers a per-call pricing model (source: Kong docs, last verified Jan 2026)"

- [ ] **Comparison has "last verified" date?**
  - ❌ "Kong doesn't support MCP"
  - ✅ "As of Jan 2026, Kong does not have MCP support (source: Kong roadmap)"

- [ ] **No negative characterizations?**
  - ❌ "Legacy API gateways like Kong are outdated"
  - ✅ "Traditional API gateways prioritize REST; STOA prioritizes agents"

- [ ] **Has compliance disclaimer?**
  - If content compares features, footer includes:
    ```
    Feature comparisons are based on publicly available documentation as of [YYYY-MM].
    Product capabilities change frequently. See [trademarks](/legal/trademarks).
    ```

### 2. Client / Customer References

- [ ] **No customer names without written permission?**
  - ❌ "Acme Corp deployed STOA on OVH and reduced latency by 40%"
  - ✅ "A 50-person SaaS company deployed STOA and reduced API latency by 40%" (anonymized)
  - ✅ "[COMPANY_NAME] reduced latency by 40%" (placeholder, real name added when approved)

- [ ] **Showcase case studies anonymized until approved?**
  - Check `.claude/rules/opsec.md` for client name allowlist
  - Real names only added with explicit email approval from customer

### 3. Compliance Claims

- [ ] **"Supports" not "Certifies"?**
  - ❌ "STOA is DORA-compliant"
  - ❌ "STOA is SOC2-certified"
  - ✅ "STOA helps organizations support DORA compliance through audit logging and RBAC"
  - ✅ "SOC2 audit checklist: [link to runbook]"

- [ ] **Regulatory disclaimer included?**
  - If content mentions compliance (GDPR, PCI-DSS, HIPAA, SOC2, DORA, NIS2):
    ```
    STOA Platform provides technical capabilities that support regulatory compliance efforts.
    This does not constitute legal advice or a guarantee of compliance. Organizations should
    consult qualified legal counsel for compliance requirements.
    ```

### 4. Security Claims

- [ ] **No security theater language?**
  - ❌ "STOA is 100% secure"
  - ❌ "Unhackable API gateway"
  - ✅ "STOA implements defense-in-depth: mTLS, RBAC, rate limiting, audit logging"

- [ ] **Threat model sections are balanced?**
  - For each threat (insider abuse, token theft, rate limit bypass), include:
    - Attacker profile (who, motivation, capability)
    - Attack vector (how)
    - STOA's defense (what we do)
    - Residual risk (what could still happen, what's out of scope)
    - Example: "Insider abuse mitigated by RBAC, but not by STOA (only by organizational controls)"

- [ ] **No "unhackable" claims?**
  - Always acknowledge residual risk, dependency on deployment, human factors

### 5. Trademark Attribution

- [ ] **Competitor product names have (TM) or (R) where applicable?**
  - Kong™ Gateway
  - MuleSoft® Anypoint
  - Google® Cloud
  - AWS®, AWS Cloud9™

- [ ] **First mention includes attribution?**
  - Include in footer or disclaimer:
    ```
    All product names and logos are trademarks of their respective owners.
    STOA Platform is not affiliated with or endorsed by any mentioned vendor.
    ```

---

## Content Type–Specific Rules

### Blog Posts (Migration Guides)

- [ ] **For each competitor migration:**
  - Has "last verified" date (not >6 months old)
  - Compares features factually (not emotionally: "legacy" banned)
  - Includes disclaimer footer
  - No explicit pricing claims
  - No "better than" language (use "different from", "alternative to")

### Blog Posts (Security Deep-Dives)

- [ ] **Threat model sections:**
  - Define attacker profile clearly
  - Explain attack vector (non-technical audience can understand)
  - State STOA's defense mechanism
  - Acknowledge residual risk ("not a silver bullet")
  - Link to security audit checklist

- [ ] **No "comparison tables: X is secure, Y is not"**
  - Each row includes source/last-verified date
  - Each row includes caveat ("depends on deployment")

### Blog Posts (Cost / ROI Analysis)

- [ ] **Cost Calculator (interactive or spreadsheet):**
  - Inputs are clearly labeled
  - Assumptions documented (e.g., "DIY cost = 0.5 FTE @ $200k/year")
  - Disclaimers: "Estimates based on median market rates, your costs may vary"
  - No competitor pricing used unless sourced + dated

### GitHub Examples Repo

- [ ] **README for each example:**
  - Clear problem statement (not comparative)
  - Implementation approach (STOA-specific)
  - How to extend (don't box users in)
  - No "vs Kong" claims (different repo for comparisons)

### Security Whitepaper

- [ ] **Threat model section:**
  - OWASP Top 10 mapped (each risk → STOA defense)
  - Residual risks clearly stated
  - Compliance framework mapping (SOC2, GDPR, PCI-DSS, HIPAA)
  - "Compliance disclaimer" in footer

- [ ] **Attack scenarios section:**
  - Realistic attack (not FUD)
  - STOA's defense explained
  - Dependencies (e.g., "assumes TLS is configured")
  - Testing steps so reader can verify

### Tutorial Content (Freelancer Guide)

- [ ] **"Getting started" content:**
  - No comparisons (save for separate "why STOA" post)
  - Purely instructional (step 1, step 2, verify)
  - Links to FAQ for "why this design choice"

### Case Studies

- [ ] **Until approved by customer:**
  - No real company name
  - No real person name
  - Use placeholders or anonymize: "A 50-person SaaS"
  - Store in stoa-strategy repo, not stoa

---

## Conflict Avoidance Matrix

### If Content Mentions...

| Topic | DO | DON'T | Rationale |
|-------|-----|-------|-----------|
| Kong | Use publicly sourced features (vs pricing) | Claim Kong is insecure | Diffamation risk |
| MuleSoft | "Alternative to MuleSoft" | "Better than MuleSoft" | Competitive language |
| Regulatory (DORA) | "Supports DORA compliance" | "DORA-compliant platform" | False certification risk |
| Security | "Defense-in-depth" approach | "100% secure" | Security theater |
| Pricing | "$50/month tier" | "$50 vs Kong's $100" | Diffamation risk |
| Client names | Anonymize or get approval | Use without permission | Privacy/contractual breach |
| Threat models | Define residual risks | Imply STOA solves all security | False claims risk |

---

## Escalation Path

### If Uncertain:
1. **Check `content-compliance.md`** for the specific scenario
2. **Ask content-reviewer in GitHub Discussions** (async, 24h response)
3. **If P0 risk (diffamation, false claims):** contact CTO before publishing

### If Violation Found (Post-Publication):
1. **P0:** Remove/correct immediately, no notification needed (privacy)
2. **P1:** Correct within 48h, note change in blog post footer ("Updated Feb 12 to clarify...")
3. **P2:** Correct in next editorial pass, no rush

---

## Content Reviewer Role (Subagent)

When content-reviewer agent reviews new content:

| Check | Pass Criteria | Block Criteria |
|-------|--------------|----------------|
| Competitor mentions | Has source + "last verified" date | No source, >6mo old |
| Compliance claims | Uses "supports" not "certified" | Claims false compliance |
| Pricing claims | No specific competitor prices | Any competitor $ claim |
| Security claims | Acknowledges residual risk | "100% secure" language |
| Customer references | Anonymized or has written approval | Real names without approval |
| Trademarks | Attribution included | Missing (TM)/(R) |

**Verdict: PASS / FIX / REJECT**

---

## Appendix: Compliance Template for New Blog Posts

Use this template to avoid compliance issues:

```markdown
---
title: "[Post Title]"
description: "[1-2 line summary]"
date: 2026-02-XX
author: "[Name]"
---

# [Post Title]

## Context
[Problem being solved, no comparisons]

## Solution
[STOA's approach, factual only]

## Implementation
[How to do this with STOA]

## Alternatives
[If mentioning competitors, include source + date]

**Disclaimer (if needed):**
[Insert relevant disclaimer from content-compliance.md]
```

---

## Tracking Compliance

### During Review (PR Template)
Add this to PR description:

```markdown
## Compliance Checklist
- [ ] No competitor pricing claims
- [ ] All competitor mentions have "last verified" date
- [ ] No false security claims ("100% secure" banned)
- [ ] No client names without approval
- [ ] Compliance claims use "supports", not "certified"
- [ ] Trademarks attributed
- [ ] Relevant disclaimer included
- [ ] content-reviewer approved
```

### Post-Publication (Monthly Audit)
Run monthly compliance scan:
```bash
# Find all blog posts and check for risky terms
grep -r "kong costs\|better than\|100% secure\|certified\|compliant" docs/blog/ stoa-web/

# Check for old "last verified" dates (>6 months)
grep -r "last verified" docs/blog/ | grep -v "2026-01\|2026-02"
```

---

## Document Metadata
- **Created:** 2026-02-11
- **Applies to:** All new content in stoa-docs, stoa-web, stoa monorepo /docs/
- **Authority:** content-compliance.md (source of truth)
- **Review cadence:** Monthly scan, quarterly audit
- **Owner:** content-reviewer subagent + CTO
