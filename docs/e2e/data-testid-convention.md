# data-testid Convention (E2E)

Internal reference for `data-testid` attributes used by E2E tests, visual regression, and ARIA-based assertions.

## Naming Pattern

```
<feature>-<element>[-<variant>]
```

- **feature**: page or feature area in kebab-case (`dashboard`, `catalog`, `subscriptions`, `marketplace`, `tenants`, `gateway`)
- **element**: the UI element (`title`, `grid`, `card`, `status`, `row`, `tab`, `chart`, `stats`, `count`, `list`)
- **variant**: optional qualifier (`servers`, `tools`, `apis`, `count`, `timestamp`, `duration`)

### Examples

| Pattern | Example |
|---------|---------|
| `<feature>-<element>` | `catalog-grid`, `dashboard-title` |
| `<feature>-<element>-<variant>` | `dashboard-gateways-count`, `subscriptions-tab-servers` |
| `<feature>-<element>-<id>` (dynamic rows) | `gateway-card-abc123`, `client-row-xyz` |

### Auto-Masked Suffixes (Visual Regression)

Values that change at runtime must use these suffixes so visual regression tests auto-mask them:

| Suffix | Meaning | Example |
|--------|---------|---------|
| `-count` | Numeric counter | `dashboard-requests-count` |
| `-timestamp` | Date/time string | `activity-last-updated-timestamp` |
| `-duration` | Elapsed time | `gateway-uptime-duration` |

## Ratchet Approach

`data-testid` attributes are added **only on components touched by tests**. Do not mass-annotate components speculatively.

Rules:
1. A new test requires `data-testid` on every element it locates by testid — add them in the same PR.
2. Never remove a `data-testid` that an existing test references.
3. Prefer ARIA-based locators (`role`, `aria-label`) over `data-testid` for interactive elements (buttons, inputs, tabs). Reserve `data-testid` for containers, counters, and non-interactive regions.
4. When adding `data-testid` to a shared component, prefix with the component name to avoid collisions (e.g., `stat-card-value` not just `value`).

## Migration Policy

- **New components** (merged after 2026-04-15): `data-testid` required per the convention above. No exceptions.
- **Existing components without tests**: no action needed — do not add testids preemptively.
- **Existing components being touched by a PR**: add missing `data-testid` to elements the PR's tests reference, following the naming pattern.
- **Conflicting names**: if an existing `data-testid` doesn't match the `<feature>-<element>[-<variant>]` pattern, leave it unless the test is being rewritten (avoid churn).

## Current Inventory

### Console (control-plane-ui)

| Page | data-testid | Element | ARIA |
|------|-------------|---------|------|
| Dashboard | `dashboard-title` | Page `h1` | — |
| Dashboard | `dashboard-kpi-grid` | KPI cards container | `role="region"` `aria-label="Platform KPIs"` |
| Dashboard | `dashboard-requests-count` | Requests StatCard | — |
| Dashboard | `dashboard-error-rate-count` | Error Rate StatCard | — |
| Dashboard | `dashboard-latency-count` | Latency P95 StatCard | — |
| Dashboard | `dashboard-gateways-count` | Gateways StatCard | — |
| Dashboard | `dashboard-traffic-chart` | Traffic sparkline section | — |
| Dashboard | `dashboard-error-chart` | Error sparkline section | — |
| Dashboard | `dashboard-gateway-instances` | Gateway instances list | — |
| Dashboard | `dashboard-top-apis` | Top APIs section | — |
| Tenants | `tenants-grid` | Tenant cards container | `role="list"` |
| Tenants | `tenant-card` | Individual tenant card | `role="listitem"` |
| Tenants | `tenant-name` | Tenant display name | — |
| Tenants | `tenant-status` | Tenant status badge | — |
| Gateways | `fleet-summary` | Fleet summary bar | — |
| Gateways | `fleet-total-count` | Total gateway count | — |
| Gateways | `gateway-cards-grid` | Gateway card grid | — |
| Gateways | `gateway-card-<id>` | Individual gateway card | — |
| Gateways | `gateway-card-status-<id>` | Status badge on card | — |

### Portal

| Page | data-testid | Element | ARIA |
|------|-------------|---------|------|
| Home | `home-header` | Welcome header + tenant badge | — |
| Home | `home-stats` | Stats cards row | — |
| Home | `home-quick-actions` | Quick action buttons | — |
| Home | `home-featured` | Featured APIs + AI tools | — |
| Home | `home-activity` | Recent activity section | — |
| API Catalog | `catalog-results-count` | Results count text | — |
| API Catalog | `catalog-grid` | API cards grid | `role="list"` `aria-label="API catalog"` |
| API Catalog | `catalog-pagination` | Pagination controls | `role="navigation"` `aria-label="Pagination"` |
| Subscriptions | `subscriptions-stats` | Stats overview region | `role="region"` `aria-label="Subscription statistics"` |
| Subscriptions | `subscriptions-active-count` | Active subs count card | `aria-label="Active Subscriptions"` |
| Subscriptions | `subscriptions-server-count` | Server subs count card | `aria-label="Server Subscriptions"` |
| Subscriptions | `subscriptions-usage-count` | Total API calls count card | `aria-label="Total API Calls"` |
| Subscriptions | `subscriptions-tab-servers` | Servers tab button | `role="tab"` `aria-selected` |
| Subscriptions | `subscriptions-tab-tools` | Tools tab button | `role="tab"` `aria-selected` |

### Missing / Gaps (as of 2026-04-15)

| Page | Missing testid | Priority |
|------|---------------|----------|
| Marketplace | Page container, items grid, search input | P2 — add when E2E tests target this page |
| Marketplace | Stats bar | P2 |
| Subscriptions | `subscriptions-tab-apis` (third tab lacks `data-testid`) | P1 — add before writing API tab tests |
| Subscriptions | Individual subscription card rows | P2 — add when row-level assertions are needed |

## Heading Hierarchy

All audited pages follow correct heading hierarchy:
- `h1`: Page title (one per page)
- `h2`: Section headings within the page
- `h3`: Card or item titles within sections

No heading-level skips (h1 → h3) found on audited pages (Dashboard, Tenants, Gateways, API Catalog, Subscriptions).

**Note on Dashboard**: Section headings inside cards use `h2` with `uppercase` styling (visually appears secondary). This is intentional — they are landmark sections within the main `h1` context.
