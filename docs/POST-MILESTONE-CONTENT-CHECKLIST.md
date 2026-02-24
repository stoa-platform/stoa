# Post-Milestone Public Content Update Checklist

> **Purpose**: Ensure STOA's public presence stays current and consistent after every significant milestone.
> **Scope**: stoa-web (gostoa.dev), stoa-docs (docs.gostoa.dev), blog posts, social channels.
> **Compliance authority**: [`.claude/rules/content-compliance.md`](../.claude/rules/content-compliance.md)
> **Content rules**: [`.claude/rules/seo-content.md`](../.claude/rules/seo-content.md)
> **Review agent**: `content-reviewer` subagent (`.claude/agents/content-reviewer.md`)

---

## Triggers — When to Run This Checklist

Run this checklist after any of the following events:

| Trigger | Examples | Priority |
|---------|----------|----------|
| **Release** | v1.x.0, major/minor version bump | P0 — same day |
| **Major Feature** | New gateway mode, OAuth 2.1, MCP protocol support | P0 — within 48h |
| **New Integration** | New adapter (Apigee, Azure APIM), new MCP client support | P1 — within 1 week |
| **Performance Milestone** | Benchmark improvement >20%, latency record | P1 — within 1 week |
| **Security Update** | CVE patch, new auth mechanism, audit certification | P0 — same day |
| **Community Event** | KubeCon, API Days, launch week, hackathon | P1 — before/after event |
| **Partnership / Logo** | New design partner, early adopter, integration partner | P1 — on announcement |

---

## Section 1 — Landing Page (gostoa.dev)

### 1.1 Hero & Positioning

- [ ] **Tagline reflects latest capabilities?**
  - Update if a new kill-feature launched (e.g., UAC, new gateway mode)
  - Max 8 words, benefit-first (not feature-first)

- [ ] **Feature highlights current?**
  - "What's New" section or feature badges updated
  - Remove deprecated/removed features

- [ ] **CTA links work?**
  - Quick start link → correct docs version
  - "Try STOA" → functional console or Docker Compose link
  - GitHub star count badge auto-refreshes (no manual update needed)

### 1.2 Competitive Comparison Table

- [ ] **Feature table rows are accurate?**
  - Each row has "last verified: YYYY-MM" comment in source
  - Claims older than 6 months must be re-verified before publish
  - Run `content-reviewer` agent on any modified row

- [ ] **No competitor pricing in table?**
  - P0 violation: any `$`, pricing tier, or cost claim about competitors
  - Use "Open Source (free)", "Enterprise (contact vendor)" — not specific prices

- [ ] **Disclaimer present?**
  ```
  Feature comparisons are based on publicly available documentation as of [YYYY-MM].
  Product capabilities change frequently. All trademarks belong to their respective owners.
  See /legal/trademarks for details.
  ```

### 1.3 Architecture / Diagram

- [ ] **Diagrams match current architecture?**
  - Gateway modes diagram matches `ADR-024` (edge-mcp current, sidecar Q2, etc.)
  - Component names match actual deployment (`stoa-gateway`, not `mcp-gateway`)

---

## Section 2 — Blog

### 2.1 Announcement Post

For every release or major feature, publish one of:

- [ ] **Release announcement** (for version bumps): News type, ≥800 words
  - Title format: "STOA Platform vX.Y — [Key Feature]"
  - Includes: what changed, why it matters, migration notes (if any), quickstart
  - Front-matter: `tags: [release, announcement]`, `unlisted: true` if pre-publishing

- [ ] **Feature deep-dive** (for major features): Tutorial type, ≥1500 words
  - Title format: "How [Feature] Works in STOA vX.Y"
  - Includes: architecture, code example, comparison to before

### 2.2 Hub & Spoke Maintenance

After publishing an announcement, update the hub articles that reference this feature:

- [ ] **Does this change affect a Hub article?**
  - Check `seo-content.md` — Pillar 1 (API Gateway Migration), Pillar 2 (MCP & AI Agents), Pillar 3 (OSS API Management)
  - If yes: update the hub's feature table or capabilities section

- [ ] **Update internal links in existing blog posts?**
  - Add cross-link from announcement to relevant spokes
  - Add cross-link from spokes to announcement (if directly relevant)

### 2.3 Compliance Pre-Check

Before any blog post goes live, run `content-reviewer` agent:

- [ ] **Competitor claims verified?**
  - Source cited, "last verified: YYYY-MM" present
  - No P0 violations (pricing, defamation, false claims)
  - See `content-compliance.md` — P0/P1/P2 categories

- [ ] **Compliance language correct?**
  - "supports DORA compliance" not "is DORA-compliant"
  - Regulatory disclaimer included if applicable

- [ ] **Build passes?**
  ```bash
  cd stoa-docs && npm run build 2>&1 | grep -E "broken|error"
  ```

---

## Section 3 — Documentation (docs.gostoa.dev)

### 3.1 Architecture & Concept Pages

- [ ] **Concept pages updated?**
  - `docs/concepts/architecture.md` — component diagram, gateway modes
  - `docs/concepts/gateway.md` — current modes, capabilities
  - `docs/concepts/mcp.md` — protocol version, supported clients

- [ ] **ADR created for architectural decision?**
  - If the milestone includes a design decision: create ADR in stoa-docs
  - Next ADR number: check `stoa-docs/docs/architecture/adr/` for highest number
  - Follow ADR template and link from implementation PR

### 3.2 API Reference

- [ ] **Swagger/OpenAPI spec updated?**
  - If new endpoints added, removed, or signatures changed
  - `docs/api/control-plane-api.md` and `docs/api/mcp-gateway-api.md`

- [ ] **Changelog / Migration section added?**
  - Breaking changes: add `docs/guides/migration/vX-to-vY.md`
  - Backwards-compatible: add note in relevant guide

### 3.3 Quick Start & Guides

- [ ] **Quick start still works end-to-end?**
  - Run through `docs/guides/quickstart` manually or via E2E smoke test
  - Docker Compose image tag matches released version

- [ ] **Guide screenshots / code blocks current?**
  - Console UI screenshots show current version
  - All `curl` examples use `${STOA_API_URL}` (not hardcoded `api.gostoa.dev`)
  - See `docs-url-convention.md` for URL zone rules

---

## Section 4 — SEO Metadata

### 4.1 Structured Data

- [ ] **JSON-LD updated on docs homepage?**
  - Version number in TechArticle schema
  - Feature list in description field

- [ ] **Sitemap regenerates on build?**
  - Confirmed by running `npm run build` (Docusaurus auto-generates)
  - Submit updated sitemap to Google Search Console after deploy

### 4.2 llms.txt

After publishing a batch of blog posts or a major release:

- [ ] **`stoa-web/public/llms.txt` updated?**
  - Add new article titles + URLs
  - Add release announcement summary

- [ ] **`stoa-web/public/llms-full.txt` updated?**
  - Add full article summaries (1–3 sentences per new article)

### 4.3 Keywords & Meta Descriptions

- [ ] **New feature keywords added to PLAN-SEO.md subject bank?**
  - If the feature has dedicated search intent (e.g., "MCP gateway tutorial"), add as topic
  - Update `stoa-docs/PLAN-SEO.md` with keyword + target article plan

---

## Section 5 — Social & Community

### 5.1 GitHub

- [ ] **Release tagged on GitHub?**
  - `gh release create vX.Y.Z --generate-notes`
  - Links to docs announcement post in release body

- [ ] **Changelog PR merged?**
  - Release Please handles this automatically on version bump commits
  - Verify: `gh run list --workflow=release-please.yml --limit 3`

### 5.2 Community Channels

- [ ] **#announcements or #release-notes channel notified?**
  - Slack / Discord message with: version, headline feature, link to blog post

- [ ] **GitHub Discussions announcement posted?**
  - Category: Announcements
  - Title: "STOA vX.Y released — [headline feature]"
  - Body: 3–5 bullet points + link to full blog post

---

## Compliance Review Step (MANDATORY)

Before any public content goes live, run the `content-reviewer` subagent:

```bash
# Trigger content-reviewer on changed files
# (Use Task tool in Claude Code with subagent_type=content-reviewer)
```

The reviewer checks for:
- P0 violations (blocking): competitor pricing, false compliance claims, undisclosed client names
- P1 issues (fix before publish): missing "last verified" dates, missing disclaimers
- P2 suggestions (non-blocking): trademark attribution, tone improvements

See `docs/CONTENT-EXPANSION-COMPLIANCE.md` for the full per-content-type checklist.

---

## Execution Workflow

```
Milestone happens
  │
  ├─ [Same day] Section 5 (GitHub release tag) + Section 3.2 (API ref if changed)
  │
  ├─ [Within 48h] Section 2.1 (Blog announcement) → content-reviewer → publish
  │                Section 1.1 (Landing page hero if needed)
  │
  ├─ [Within 1 week] Section 3.1 (Architecture docs) + Section 3.3 (Guides)
  │                   Section 1.2 (Comparison table if new features)
  │                   Section 4.1 (SEO metadata)
  │
  └─ [Next blog batch] Section 4.2 (llms.txt update)
                        Section 4.3 (PLAN-SEO.md keyword bank)
```

---

## Quick Reference: Who Does What

| Section | Owner | Reviewer |
|---------|-------|----------|
| Landing page (stoa-web) | Platform team | content-reviewer agent |
| Blog posts (stoa-docs) | docs-writer agent + Platform team | content-reviewer agent |
| Architecture docs | Platform team | docs-writer agent |
| ADRs | Architect | docs-writer agent |
| API Reference | Engineer | — |
| llms.txt | Platform team | — |
| GitHub Release | Engineer | — |
| Community channels | Platform team | — |

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Content compliance rules | `.claude/rules/content-compliance.md` | P0/P1/P2 violation reference |
| SEO content strategy | `.claude/rules/seo-content.md` | Blog templates, hub & spoke model |
| Documentation strategy | `.claude/rules/documentation.md` | Where docs live, ADR numbering |
| Compliance checklist | `docs/CONTENT-EXPANSION-COMPLIANCE.md` | Per-content-type pre-publication checks |
| SEO tracking | `docs/SEO-TRACKING.md` | Keyword rankings, GSC monitoring |

---

## Document Metadata

- **Created**: 2026-02-24
- **Applies to**: All public-facing content updates post-milestone
- **Linked from**: `docs/runbooks/README.md`
- **Review cadence**: Update when new content channels are added or triggers change
- **Owner**: Platform team + content-reviewer subagent
