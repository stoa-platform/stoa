# SEO Tracking — Weekly Process

> Internal ops document. Covers Google Search Console monitoring, Looker Studio dashboard, and weekly data archiving for docs.gostoa.dev.

## Property

| Item | Value |
|------|-------|
| **GSC Property** | `docs.gostoa.dev` (URL prefix) |
| **Owner** | admin@gostoa.dev (verified) |
| **Sitemap** | `https://docs.gostoa.dev/sitemap.xml` (submitted) |
| **Looker Studio** | *(URL to be added after setup)* |
| **Archive Sheet** | *(URL to be added after setup)* |

## Sitemap Configuration (verified 2026-02-16)

Docusaurus generates `sitemap.xml` automatically via `@docusaurus/plugin-sitemap`:

| Setting | Value |
|---------|-------|
| `lastmod` | `date` (file modification date) |
| `changefreq` | `weekly` (default) |
| `filename` | `sitemap.xml` |
| Homepage priority | **1.0** (daily) |
| `/docs/*` priority | **0.8** |
| `/blog/*` priority | **0.6** |
| Ignored | tags, pagination, archive, category pages |

## Meta Description Audit (verified 2026-02-16)

**32/32 blog posts**: all have meta descriptions, 80-160 chars. Average ~128 chars.
**Key docs pages** (intro, roadmap, FAQ, migration guides): all have meta descriptions.

No gaps found. Next audit: when blog batch 7 publishes.

## Looker Studio Dashboard

### Setup (one-time)

1. Go to [Looker Studio](https://lookerstudio.google.com/)
2. **Create → Data Source → Google Search Console**
3. Select site: `docs.gostoa.dev` (URL impression)
4. Create report with 4 views:

| View | Chart Type | Dimensions | Metrics | Filter |
|------|-----------|------------|---------|--------|
| **Impressions & Clicks / week** | Time series | `Date` (week) | Impressions, Clicks, CTR | Last 16 months |
| **Top Pages by Position** | Table | `Page` | Avg Position, Impressions, Clicks | Top 25 |
| **Top Queries by Impressions** | Table | `Query` | Impressions, Clicks, CTR, Avg Position | Top 50 |
| **Geographic Distribution** | Geo map + table | `Country` | Impressions, Clicks | All |

5. Add filters: date range selector, country, device
6. Share link → paste URL in the Property table above

### Key Metrics to Watch

| Metric | Baseline (Feb 16, 2026) | Target (Mar 31) | Why |
|--------|------------------------|------------------|-----|
| Total impressions/week | ~24 | 500+ | Community launch + blog batch effect |
| Indexed pages | ~4 | 40+ | 32 blog posts + key docs should be indexed |
| Avg position (top queries) | ~4-8 | <10 | Maintain ranking as competition increases |
| CTR | TBD | >2% | Industry average for tech blogs |

## Weekly Archive (Google Sheets)

### Sheet Structure

Create a Google Sheet with 4 tabs:

**Tab 1: `Weekly_Summary`**

| Column | Example |
|--------|---------|
| `snapshot_date` | 2026-02-17 |
| `total_impressions` | 24 |
| `total_clicks` | 3 |
| `avg_ctr` | 12.5% |
| `avg_position` | 6.2 |
| `indexed_pages` | 4 |
| `total_pages_in_sitemap` | ~100 |

**Tab 2: `Pages`**

| Column | Example |
|--------|---------|
| `snapshot_date` | 2026-02-17 |
| `page_url` | /blog/webmethods-migration-guide |
| `impressions` | 8 |
| `clicks` | 1 |
| `ctr` | 12.5% |
| `avg_position` | 6.4 |

**Tab 3: `Queries`**

| Column | Example |
|--------|---------|
| `snapshot_date` | 2026-02-17 |
| `query` | webmethods migration |
| `impressions` | 5 |
| `clicks` | 1 |
| `ctr` | 20% |
| `avg_position` | 4.2 |

**Tab 4: `Countries`**

| Column | Example |
|--------|---------|
| `snapshot_date` | 2026-02-17 |
| `country` | France |
| `impressions` | 10 |
| `clicks` | 2 |

### Weekly Snapshot Process

**When**: Monday morning (before 10:00)
**Who**: Christophe or Claude (manual for now, Apps Script V2 later)
**Duration**: ~5 minutes

1. Open [Google Search Console](https://search.google.com/search-console?resource_id=https://docs.gostoa.dev/)
2. Set date range: **last 7 days** (Mon-Sun of previous week)
3. **Performance → Search results**:
   - Export CSV → paste into `Weekly_Summary` (totals) + `Queries` (top 50)
   - Switch to **Pages** tab → export → paste into `Pages`
   - Switch to **Countries** tab → export → paste into `Countries`
4. **Indexing → Pages**: note "Indexed" count → add to `Weekly_Summary.indexed_pages`
5. Check for any **Coverage errors** → fix if blocking (usually stale URLs)

### Data Retention

- Google Search Console retains **16 months** of data
- The Sheet is the long-term archive — never delete rows
- First snapshot captures the pre-community-launch baseline (critical for measuring impact)

## Docusaurus SEO Checklist (per blog batch)

Run after every blog batch publish:

```bash
cd stoa-docs

# 1. Build — catches broken links + validates frontmatter
npm run build

# 2. Verify all blog posts have descriptions
grep -rL '^description:' blog/ --include='*.md'
# Must return empty

# 3. Check description lengths
for f in blog/**/*.md blog/*.md; do
  desc=$(grep '^description:' "$f" | sed 's/^description: //')
  len=${#desc}
  if [ "$len" -gt 0 ] && ([ "$len" -lt 80 ] || [ "$len" -gt 160 ]); then
    echo "WARNING: $f — description length $len (target: 80-160)"
  fi
done

# 4. Verify sitemap includes new pages
curl -s https://docs.gostoa.dev/sitemap.xml | grep -c '<url>'
# Should increase after deploy
```

## Automation Roadmap (V2)

When manual snapshots become tedious (~4 weeks), automate with Google Apps Script:

1. **Apps Script** in the archive Sheet
2. Use [Search Console API](https://developers.google.com/webmaster-tools/v1/api_reference) (`searchAnalytics.query`)
3. Trigger: weekly (Monday 08:00 UTC)
4. Scope: `https://docs.gostoa.dev/` (same property)
5. No cost (GSC API is free, Apps Script free tier sufficient)

Not in scope for this ticket — evaluate after 4 weekly snapshots confirm the process works.
