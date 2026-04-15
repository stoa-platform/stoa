<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
globs: "blog/**,docs/**,*.mdx"
---

# SEO Content & Community Strategy

## Content Types

| Type | Cadence | Min Words | SEO Pattern |
|------|---------|-----------|-------------|
| Tutorial | Weekly (Tue) | 1500 | Long-tail, step-by-step, code blocks |
| Comparison | Biweekly (Thu) | 1200 | vs-keyword, feature tables, disclaimers |
| Glossary | Monthly | 2000 | A-Z, dense internal links |
| News/Update | Monthly | 800 | Timely, short, link-rich |

## Front-Matter (mandatory)

```yaml
---
slug: <kebab-case-seo-url>
title: "<Keyword-First (max 60 chars)>"
description: "<Pain point opener (max 155 chars)>"
authors: [stoa-team]
tags: [<2-5 from tags.yml>]
unlisted: true          # ADD if date > today, REMOVE when date arrives
keywords: [<primary>, <3-5 secondary>]
---
<!-- last verified: YYYY-MM -->
```

Title: keyword-first, max 60 chars, power words (vs/benchmark/migrate), no brand, year when relevant, numbers when possible. Description: pain point opener, practitioner tone, no filler.

## Scheduled Posts

Future-dated posts get `unlisted: true` (not `draft: true` — keeps URLs alive for cross-links). `scripts/manage-scheduled-posts.sh` manages this. Daily CI cron publishes when date arrives.

Tags: `release, announcement, feature, security, breaking-change, mcp, community, roadmap, architecture, migration, compliance, comparison, ai, open-source, tutorial, education, docker, quickstart, api-gateway`. Never invent — add to `blog/tags.yml` first. Filename: `blog/YYYY-MM-DD-<slug>.md`.

## Hub & Spoke (3 Pillars)

| Pillar | Hub | Spokes |
|--------|-----|--------|
| API Gateway Migration | `api-gateway-migration-guide-2026` | 8 (webMethods, MuleSoft, DataPower, Apigee, Kong, Axway, WSO2, Layer7) |
| MCP & AI Agents | `what-is-mcp-gateway` | 3 published + 2 TODO |
| Open Source API Mgmt | `open-source-api-gateway-2026` | 7 (sovereignty, DORA, multi-tenant, Apache-2, API keys, security, GitOps) |

Rules: every spoke links to hub, every hub links to all spokes, cross-pillar encouraged, never guess links (verify with `npm run build`).

## Quality Gates

10 checks: build clean, front-matter complete, word count met, min 3 internal links, hub link present, content compliance (no P0/P1), last-verified tag on comparisons, valid tags, no broken links, answer-first format. Pre-commit: `cd stoa-docs && npm run build 2>&1 | grep -E "broken|error|warning"` → must be empty.

## Blog Validation Process (MANDATORY)

Every blog article MUST pass these gates before merge:

```
1. Write article (docs-writer or manual)
2. npm run build (link validation)
3. content-reviewer audit (ALWAYS — not just when competitors mentioned)
4. scripts/audit-content-compliance.sh (automated P0/P1 scan)
5. CI: docs-audit.yml runs both client-names + content-compliance jobs
```

**Gate enforcement**:
- `audit-content-compliance.sh` runs in CI on every PR touching `blog/**`
- P0 = merge blocked (competitor pricing, certification claims, client names)
- P1 = warning in PR comment (unsourced claims, missing disclaimers, negative characterizations)
- Local pre-check: `cd stoa-docs && ./scripts/audit-content-compliance.sh`

**content-reviewer subagent is ALWAYS required** — not just when competitors are mentioned. Cost claims, regulatory language, and positioning can violate P1 even without naming competitors.

## Subagent Pattern

Blog post flow: choose topic → research → prepare context for `docs-writer` (front-matter, valid link list, hub, word count, compliance rules) → generate → `npm run build` (ALWAYS — subagents guess wrong links) → **`content-reviewer` (ALWAYS)** → `audit-content-compliance.sh` → fix → commit.

## Search Optimization

Already implemented: llms.txt, JSON-LD (TechArticle + BreadcrumbList), sitemap. Rules: answer-first format, FAQ section (3-5 Q&A), structured H2/H3, code blocks, comparison tables, anchor links. Update llms.txt after each blog batch.

## Community Strategy

Tactics: launch weeks (quarterly, 5 features over 5 days), community spotlights (monthly), changelogs (per release), GitHub Discussions. GSC monitoring weekly (indexation >80%, CTR >2%). Never name clients without authorization. Credit contributors by GitHub handle. Editorial calendar in `PLAN-SEO.md` (stoa-docs repo).
