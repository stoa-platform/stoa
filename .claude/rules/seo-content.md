---
description: SEO content generation — blog templates, hub & spoke model, editorial calendar, quality gates
globs: "docs/**,blog/**"
---

# SEO Content & Community Strategy

## Scope

Rules for generating blog posts, documentation, and community content on **stoa-docs** (docs.gostoa.dev). Complements `content-compliance.md` (legal/competitive rules) and `documentation.md` (where docs live).

## A. Content Types & Templates

### 4 Content Types

| Type | Cadence | Target Audience | SEO Pattern | Min Words |
|------|---------|----------------|-------------|-----------|
| **Tutorial** | Weekly (Tue) | Developers searching "how to X" | Long-tail keywords, step-by-step, code blocks | 1500 |
| **Comparison** | Biweekly (Thu) | Architects evaluating alternatives | vs-keyword, feature tables, disclaimers | 1200 |
| **Glossary** | Monthly | Beginners searching definitions | A-Z format, dense internal links | 2000 |
| **News/Update** | Monthly | Community staying current | Timely, short, link-rich | 800 |

### Front-Matter Template (mandatory for all blog posts)

```yaml
---
slug: <kebab-case-seo-url>
title: <Title with Primary Keyword (max 65 chars)>
description: <Meta description 120-160 chars with primary keyword>
authors: [stoa-team]
tags: [<2-5 from tags.yml>]
unlisted: true          # ← ADD if post date > today, REMOVE when date arrives
keywords:
  - <primary keyword>
  - <3-5 secondary keywords>
  - <2-3 long-tail variations>
---
<!-- last verified: YYYY-MM -->
```

**Rules**:
- `slug` = URL-friendly, keyword-rich, no dates (Docusaurus prepends date from filename)
- `title` must contain the primary keyword, ideally near the start
- `description` = the meta description Google shows; 120-160 chars, include primary keyword
- `tags` = only tags that exist in `blog/tags.yml` (build fails otherwise)
- `unlisted` = **MANDATORY** for future-dated posts (date > today). Omit for posts publishing today
- `keywords` = for SEO research tracking, not rendered but used by AI Factory to plan content
- `<!-- last verified: YYYY-MM -->` = required on any article with comparative claims

### Scheduled Posts (Future-Dated Articles)

Docusaurus has no native scheduling. STOA uses a prebuild script + daily CI cron.

**How it works**:
1. `scripts/manage-scheduled-posts.sh` runs before every build (`prebuild` hook)
2. Posts with future dates get `unlisted: true` (hidden from listings/feeds, but URL works)
3. When the date arrives, the daily CI cron rebuilds and removes `unlisted: true`
4. Posts with manual `draft: true` are never touched by the script

**Rules for AI Factory (MANDATORY when writing blog posts)**:
- When creating a blog post with a future date, ALWAYS add `unlisted: true` in frontmatter — Claude handles this, the prebuild script is only a safety net
- When the post date is today or past, do NOT add `unlisted: true`
- When creating a post that should stay hidden regardless of date (e.g., unreleased feature), use `draft: true`
- Never use both `draft: true` and `unlisted: true` — Docusaurus forbids it
- After writing any blog post, always run `npm run build` to verify (the prebuild hook also runs the script as double-check)

**Why unlisted (not draft)**:
- `draft: true` hides the post completely — breaks cross-links from published posts
- `unlisted: true` keeps the URL alive — cross-links work, but post is hidden from listings/RSS/sitemap
- This matches the Vercel/Supabase "launch week" pattern for pre-published content

**Commands**:
```bash
./scripts/manage-scheduled-posts.sh --status  # See all posts with dates + visibility
./scripts/manage-scheduled-posts.sh --check   # Dry-run: what would change?
./scripts/manage-scheduled-posts.sh --apply   # Apply changes (run by prebuild)
```

### Available Tags (from `blog/tags.yml`)

```
release, announcement, feature, security, breaking-change, mcp, community,
roadmap, architecture, migration, compliance, comparison, ai, open-source,
tutorial, education, docker, quickstart, api-gateway
```

Never invent tags. If a new tag is needed, add it to `blog/tags.yml` first.

### Article Filename Convention

```
blog/YYYY-MM-DD-<slug>.md
```

Example: `blog/2026-02-18-kong-vs-stoa-mcp-gateway.md`

For articles with images, use directory format:
```
blog/YYYY-MM-DD-<slug>/index.md
blog/YYYY-MM-DD-<slug>/diagram.png
```

## B. Hub & Spoke Model (Pillar-Cluster SEO)

Every article belongs to a content pillar. Hubs are comprehensive articles; spokes are focused sub-topics that link back to the hub.

### Pillar 1: API Gateway Migration

| Role | Article | Status |
|------|---------|--------|
| **Hub** | `api-gateway-migration-guide-2026` | Published |
| Spoke | `webmethods-migration-guide` | Published |
| Spoke | `mulesoft-migration-open-source-gateway` | Published |
| Spoke | `datapower-tibco-migration-guide` | Published |
| Spoke | `apigee-alternative-open-source` | Published |
| Spoke | `stoa-vs-kong-api-gateway` | Published |
| Spoke | `axway-api-gateway-migration-open-source` | Published |
| Spoke | `wso2-api-manager-open-source-alternative` | Published |
| Spoke | `layer7-ca-api-gateway-migration-stoa` | Published (PR #68) |

### Pillar 2: MCP & AI Agents

| Role | Article | Status |
|------|---------|--------|
| **Hub** | `what-is-mcp-gateway` | Published |
| **Hub** | `connecting-ai-agents-enterprise-apis` | Published |
| Spoke | `mcp-gateway-quickstart-docker` | Published |
| Spoke | `esb-is-dead-long-live-mcp` | Published |
| Spoke | `api-gateway-glossary-2026` | Published |
| Spoke | MCP protocol deep-dive (architecture) | TODO |
| Spoke | AI agent security patterns | TODO |

### Pillar 3: Open Source API Management

| Role | Article | Status |
|------|---------|--------|
| **Hub** | `open-source-api-gateway-2026` | Published |
| Spoke | `api-management-europe-sovereignty` | Published |
| Spoke | `dora-nis2-api-gateway-compliance` | Published |
| Spoke | `multi-tenant-api-gateway-kubernetes` | Published |
| Spoke | `why-apache-2-not-bsl` | Published |
| Spoke | `api-keys-in-git-history` | Published |
| Spoke | `api-security-checklist-solo-dev` | Published |
| Spoke | `gitops-in-10-minutes` | Published |

### Linking Rules

1. **Every spoke MUST link to its hub** (at least once, ideally in intro + conclusion)
2. **Every hub MUST link to all its published spokes** (update hub when new spoke published)
3. **Cross-pillar links encouraged** (e.g., migration article links to MCP tutorial)
4. **Docs cross-links**: blog posts should link to relevant `/docs/` pages when deeper reference exists
5. **Never guess internal links** — verify paths exist before committing (see Section D)

### Valid Internal Link Paths (reference)

Blog posts link to each other using relative paths:
```markdown
[MCP Gateway Guide](/blog/what-is-mcp-gateway)
[Docker Tutorial](/blog/mcp-gateway-quickstart-docker)
```

Docs pages use full paths:
```markdown
[Quick Start](/docs/guides/quick-start)
[Architecture Overview](/docs/concepts/architecture)
[Migration Guide](/docs/guides/migration/)
[ADR-024 Gateway Modes](/docs/architecture/adr/adr-024-gateway-unified-modes)
```

## C. Quality Gates (Content-Specific)

Run these checks before committing any blog post or docs change.

| # | Check | Pass Criteria | Verification |
|---|-------|---------------|-------------|
| 1 | Build clean | Zero errors, zero broken links | `npm run build` in stoa-docs |
| 2 | Front-matter complete | `slug`, `title`, `description`, `tags`, `keywords` all present | Grep front-matter fields |
| 3 | Word count | Tutorial >=1500, Comparison >=1200, Glossary >=2000, News >=800 | `wc -w <file>` |
| 4 | Internal links | Min 3 internal links per article | Manual count |
| 5 | Hub link present | Article links to its pillar hub | Grep for hub slug |
| 6 | Content compliance | Zero P0/P1 violations | `content-reviewer` agent scan |
| 7 | Last verified tag | Present on any comparative claim | Grep `<!-- last verified` |
| 8 | Tags valid | All tags exist in `tags.yml` | `npm run build` (catches invalid tags) |
| 9 | No broken links | All internal links resolve | `npm run build` (Docusaurus reports broken links) |
| 10 | Answer-first format | Article starts with 2-3 sentence summary | Manual check (intro before `<!-- truncate -->`) |

### Pre-Commit Checklist

```bash
cd stoa-docs
npm run build 2>&1 | grep -E "broken|error|warning"
# Must return empty (zero issues)
```

## D. Subagent Delegation Pattern for Content

### Pattern: Blog Post Generation

```
1. [Inline] Choose article type + topic from PLAN-SEO.md or editorial calendar
2. [Inline] Research: identify target keywords, existing content, hub to link
3. [Inline] Prepare context package for docs-writer (see below)
4. [docs-writer/sonnet] Generate article draft
5. [Inline] ALWAYS run `npm run build` in stoa-docs after writing
6. [Inline] Fix broken links (subagents WILL guess wrong paths)
7. [content-reviewer/sonnet] Compliance scan (if article mentions competitors)
8. [Inline] Fix any P0/P1 violations
9. [Inline] Commit + PR (Ship mode for blog posts, Show for structural changes)
```

### Context Package for docs-writer

When delegating to `docs-writer`, ALWAYS provide:

1. **Front-matter template** (filled with chosen topic, keywords, tags)
2. **Valid link list** — extract from build or provide known-good paths:
   ```
   Blog: /blog/what-is-mcp-gateway, /blog/open-source-api-gateway-2026, ...
   Docs: /docs/guides/quick-start, /docs/concepts/architecture, ...
   ```
3. **Hub article** — which pillar hub to link back to
4. **Word count target** — minimum for the content type
5. **Compliance summary** — "no pricing, no 'better than', disclaimer required if comparing"
6. **Existing articles** — list of published articles to avoid duplication

### Critical Gotcha: Subagents Guess Wrong Links

Subagents do NOT have the stoa-docs sitemap in context. They WILL invent paths like `/docs/guides/mcp-protocol` when the real path is `/docs/guides/fiches/mcp-protocol`.

**Prevention**:
- Always provide a valid link list in the context package
- Always run `npm run build` after subagent writes (catches broken links)
- Never skip the build step, even for "simple" articles

## E. Search Everywhere Optimization

Optimize for both traditional search (Google) AND AI engines (ChatGPT, Claude, Perplexity).

### Already Implemented
- **llms.txt** on stoa-web (gostoa.dev/llms.txt, gostoa.dev/llms-full.txt)
- **JSON-LD** on stoa-docs: TechArticle + BreadcrumbList on every page
- **Sitemap** auto-generated by Docusaurus, submitted to GSC

### Content Format Rules

| Rule | Why | How |
|------|-----|-----|
| **Answer-first** | Featured snippet + AI citation | Start every article with 2-3 sentence summary answering the title question |
| **FAQ section** | People Also Ask + AI training | Add `## FAQ` with 3-5 Q&A pairs at end of tutorials and comparisons |
| **Structured headings** | Crawlability + AI parsing | Use H2/H3 hierarchy, never skip levels, use keywords in headings |
| **Code blocks** | Developer search intent | Include runnable code examples in tutorials |
| **Tables** | Scannable + AI-extractable | Use comparison tables for feature comparisons |
| **Internal anchor links** | Deep linking + navigation | Add `{#section-id}` anchors for key sections |

### FAQ Template

```markdown
## FAQ

### What is [topic]?
[2-3 sentence definition. Link to glossary or concept page.]

### How does [topic] compare to [alternative]?
[Brief comparison. Link to comparison article if exists.]

### Can I use [topic] with [technology]?
[Yes/no with brief explanation. Link to relevant tutorial.]
```

### llms.txt Updates

After publishing a batch of blog posts, update:
1. `stoa-web/public/llms.txt` — add new article titles + URLs
2. `stoa-web/public/llms-full.txt` — add article summaries

Cadence: after every blog batch (not per-article).

## F. Community Strategy

### Tactics (Supabase/Vercel-inspired)

| Tactic | Implementation | Cadence |
|--------|---------------|---------|
| **Launch Week** | Bundle 5 features, daily blog post for 1 week | Quarterly |
| **Community Spotlight** | Blog post featuring OSS contributor or early adopter | Monthly |
| **Changelog** | Public changelog blog post per release | Per release |
| **GitHub Discussions** | Respond to issues, feature requests, Q&A | Ongoing |
| **llms.txt refresh** | Update AI discovery files with new content | Per blog batch |
| **GSC monitoring** | Check indexation, impressions, CTR, coverage | Weekly |

### Launch Week Template

```
Monday:    Feature announcement #1 (blog + demo GIF)
Tuesday:   Feature announcement #2 (blog + code example)
Wednesday: Technical deep-dive (ADR or architecture post)
Thursday:  Community spotlight or migration success story
Friday:    Recap + roadmap preview
```

### GSC Monitoring Checklist (weekly)

1. **Indexation**: pages indexed vs submitted (target: >80%)
2. **Impressions**: week-over-week trend (target: growing)
3. **CTR**: average click-through rate (target: >2%)
4. **Coverage errors**: fix any crawl errors immediately
5. **Top queries**: identify new keyword opportunities

### Community Content Rules

- **Spotlight posts** require explicit permission from the featured person/org
- **Never name clients** without written authorization (see `opsec.md`)
- Use "an enterprise customer" or "a European financial institution" for anonymized references
- **Discord/Slack invites**: only link to official channels listed in stoa-docs community page
- **Contributor recognition**: always credit by GitHub handle, link to their PR

## G. Editorial Calendar Integration

See `PLAN-SEO.md` in stoa-docs repo for:
- Pre-researched topic bank (40+ topics with target keywords)
- Weekly rotation: Tutorial (Tue) -> Comparison (Thu biweekly) -> Glossary (monthly) -> News (monthly)
- Seasonal hooks: DORA deadlines (Q1), KubeCon (Q2), year-in-review (Q4)

### How to Pick the Next Article

1. Check `PLAN-SEO.md` subject bank for next unclaimed topic
2. Verify the hub & spoke mapping — prioritize spokes for incomplete pillars
3. Check GSC for keyword opportunities (queries with impressions but low CTR)
4. If a hub has <3 spokes, prioritize spoke creation over new hubs
5. Mark chosen topic as "in progress" in PLAN-SEO.md before writing
