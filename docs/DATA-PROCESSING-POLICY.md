# Data Processing Policy — STOA AI Factory

**Version**: 1.0
**Date**: 2026-03-02
**Classification**: Internal — Contractual Annex

---

## 1. Data Classification & Handling Rules

| Data Type | Classification | Storage | Transit | Rule |
|-----------|---------------|---------|---------|------|
| STOA source code (OSS) | Public | Anywhere | US/EU providers | API-only mode, zero-retention, non-training |
| HEGEMON prompts & orchestration logic | Confidential — CAB | CAB-controlled infra | Layer separation enforced | Proprietary logic never sent to external models |
| Client code & data | Confidential — Client | Client infra / EU-only | EU or on-prem only | Written agreement required before any processing |
| STOA-bench datasets | Public | Open source | Anywhere | Synthetic tasks only, no real client data |
| Credentials, tokens, secrets | Critical | Vault only (Infisical) | Never in prompts | Absolute, no exceptions |

## 2. Sovereignty Routing Modes

| Mode | Scope | Authorized Providers | Data Residency |
|------|-------|---------------------|----------------|
| **Mode 1 — STOA Development** | Internal R&D on open-source code | US/EU LLM providers (Anthropic, OpenAI, Mistral) | US or EU |
| **Mode 2 — Client Delivery** | Client project execution | EU-only providers (Mistral Paris, Llama self-hosted) | EU exclusively |
| **Mode 3 — Air-Gapped** | Regulated environments (banking, defense) | Client network only, no external calls | Client premises only |

The routing mode is determined per engagement and documented in the project contract. Mode escalation (e.g., Mode 1 to Mode 2) requires written client approval.

## 3. Absolute Rules

1. **No credentials in prompts** — API keys, tokens, passwords, and secrets must never appear in any LLM prompt, context window, or training data. Violations trigger immediate incident response.
2. **Client code stays in-region** — Client source code and proprietary data never transit to US-based providers without explicit written agreement specifying the provider, data scope, and retention policy.
3. **Prompt isolation** — HEGEMON orchestration prompts (proprietary business logic) are separated from model payloads. Model providers receive only the task-specific context, never the orchestration layer.
4. **Operator certification** — Every operator (human or automated agent) accessing the AI Factory must acknowledge this policy before being granted access.

## 4. Technical Enforcement

| Control | Implementation |
|---------|---------------|
| Secret detection | Gitleaks pre-commit hook + CI scan on every push |
| PII middleware | Gateway-level regex + pattern matching, blocks sensitive data in transit |
| Prompt logging | All LLM interactions logged (without secrets) for audit trail |
| Access control | RBAC (4 roles) + per-subscription API keys + mTLS for gateway-to-gateway |
| Retention | Zero-retention agreements with all LLM providers (API-only, no training) |

## 5. Compliance

This policy supports alignment with:
- **GDPR** (EU 2016/679) — data minimization, purpose limitation, storage limitation
- **DORA** (EU 2022/2554) — ICT risk management, third-party provider oversight
- **AI Act** (EU 2024/1689) — transparency, human oversight, data governance

This document does not constitute legal advice or guarantee regulatory compliance. Organizations should consult qualified legal counsel for specific compliance requirements.

---

**Signature**: ___________________________

**Name**: ___________________________

**Date**: ___________________________

**Organization**: ___________________________
