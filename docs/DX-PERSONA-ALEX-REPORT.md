# DX Test Report — Persona Alex

> **Date**: 2026-02-15
> **Ticket**: CAB-1035
> **Persona**: Alex, 28 ans, freelance JS/Python, discovers STOA today
> **Constraint**: Only public docs + URLs, zero internal knowledge
> **Protocol**: 7-step journey, each step timed + friction logged

## Executive Summary

| Metric | Value |
|--------|-------|
| **Time-to-First-Tool-Call** | **INFINITE** (blocked at Step 3) |
| **Blockers** | 1 critical (no self-registration) |
| **Friction points** | 13 total (1 critical, 4 high, 5 medium, 3 low) |
| **Abandon points** | 2 (Step 3 Keycloak wall, Step 4 Quick Start confusion) |
| **Verdict** | **NO-GO** for developer self-service onboarding |

## Journey

### Step 1: Landing page (gostoa.dev) — OK (~1 min)

**What Alex sees**: Clear value prop ("gateway purpose-built for AI agents"), pricing with free tier, multiple CTAs.

**Frictions**:
- **F1** (Medium): "UAC (Universal API Contract)" used without definition — Alex: "c'est quoi?"
- **F2** (Medium): "MCP Protocol" assumed known — a JS/Python dev may not know what Model Context Protocol is

**Positive**: Design is clean, 3-tier pricing is clear, "Try STOA Free" CTA is prominent.

### Step 2: Find how to install/access — Partial (~2 min)

**What Alex does**: Clicks "Try STOA Free" → portal.gostoa.dev. Also finds "Read the Quickstart" → docs.

**Frictions**:
- **F3** (Low): Two CTAs ("Try STOA Free" vs "Read the Quickstart") — which one first?

### Step 3: Create account / access portal — BLOCKED

**What Alex sees**: portal.gostoa.dev → Keycloak login page → **no registration link**.

**F4 — CRITICAL BLOCKER**: Keycloak self-registration is DISABLED. Alex cannot create an account. The "Try STOA Free" CTA leads to a dead end. The only way to get access is admin provisioning or emailing `demo@gostoa.dev`.

> Alex closes the tab. Journey ends here.

**Impact**: The entire developer self-service promise ("Community: Full platform, no limits") is broken. Alex expected a sign-up flow like Stripe/Vercel/Supabase.

### Step 4: Quick Start guide — Confusing (if Alex persists)

**URL**: docs.gostoa.dev/docs/guides/quickstart

**Frictions**:
- **F5** (High): Three parallel paths (AI-First, Console, API) with no recommendation for which to start with
- **F6** (High): No account creation procedure — guide assumes Alex already has STOA access
- **F7** (High): `CLIENT_ID` and `CLIENT_SECRET` referenced in curl commands but no explanation of where to get them
- **F8** (Medium): "5 Minutes" title is misleading — realistic time is 15-30 min minimum (if you have credentials)
- **F9** (Low): No screenshots or visual guides

### Step 5: Browse MCP tools catalog — BLOCKED (needs account)

### Step 6: Subscribe to a tool — BLOCKED (needs account + admin approval)

**F10** (Medium): Even with an account, subscriptions require admin approval (no ETA shown to Alex).

### Step 7: Make first tool call — BLOCKED (needs credentials)

**Additional frictions from MCP guide** (docs.gostoa.dev/docs/guides/mcp-getting-started):
- **F11** (High): Prerequisites assume `kubectl` + running cluster + active tenant — enterprise setup, not dev-friendly
- **F12** (Medium): Multi-step OAuth2 token flow for a simple tool call (5 commands before first real request)
- **F13** (Low): No end-to-end "zero to tool call" example for developers

## Friction Summary

| # | Friction | Severity | Step | Type |
|---|---------|----------|------|------|
| F4 | No Keycloak self-registration | **CRITICAL** | 3 | Blocker |
| F5 | Quick Start: 3 paths, no recommendation | High | 4 | Confusion |
| F6 | Quick Start: no account creation docs | High | 4 | Missing |
| F7 | Quick Start: CLIENT_ID/SECRET sourcing unclear | High | 4 | Missing |
| F11 | MCP guide assumes kubectl + cluster | High | 7 | Wrong audience |
| F1 | Landing: "UAC" undefined | Medium | 1 | Jargon |
| F2 | Landing: "MCP" assumed known | Medium | 1 | Jargon |
| F8 | Quick Start: "5 min" is misleading | Medium | 4 | Expectation |
| F10 | Subscription needs admin approval, no ETA | Medium | 6 | Flow |
| F12 | OAuth2 token flow too complex for dev | Medium | 7 | Complexity |
| F3 | Two CTAs on landing, no priority | Low | 2 | Confusion |
| F9 | No screenshots in Quick Start | Low | 4 | Polish |
| F13 | No zero-to-tool-call example | Low | 7 | Missing |

## Root Cause Analysis

STOA's onboarding is designed for **B2B enterprise** (admin provisions consumers) not for **developer self-service** (Alex signs up alone). The architecture makes sense for enterprise customers but violates the "Community: Free, no limits" promise on the pricing page.

The Cycle 5 signal was correct:
> "Optimised enterprise infrastructure (mTLS, Vault, RBAC, OPA) without validating the user journey discovery → first tool call"

## Recommendations

### P0 — Must fix before claiming "developer-friendly"

1. **Enable Keycloak self-registration** for the `stoa` realm (or create a `developers` realm with self-signup)
2. **Auto-approve subscriptions** for free-tier APIs (no admin gate for standard plans)
3. **Single golden path** in Quick Start: "Step 1: Sign up, Step 2: Get key, Step 3: Call API" — 3 commands max

### P1 — Should fix for demo credibility

4. **Quick Start rewrite**: One path only, credentials inline, copy-paste works
5. **MCP guide for developers**: Zero prerequisites (no kubectl), use hosted cloud
6. **Define jargon**: Tooltips or glossary links for UAC, MCP, tenant on landing

### P2 — Nice to have

7. **Interactive "Try It" playground** (like Stripe API explorer)
8. **Screenshot walkthrough** for portal subscription flow
9. **"Time to first API call" badge** (target: < 5 min)

## Verdict

| Criteria | Status |
|----------|--------|
| Test performed (1h max) | Done (simulated, all 7 steps attempted) |
| Friction notes documented | 13 frictions logged |
| TTFTC measured | INFINITE (blocked at Step 3) |
| Go/NoGo for automated test | **NO-GO** — cannot automate a flow that requires admin provisioning |
