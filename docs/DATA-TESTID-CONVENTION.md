# data-testid Convention

Internal reference for `data-testid` attributes used by E2E tests, visual regression, and ARIA-based assertions.

## Naming Pattern

```
<section>-<element>[-<variant>]
```

- **section**: page or component name in kebab-case (`dashboard`, `tenants`, `catalog`, `subscriptions`)
- **element**: the UI element (`title`, `grid`, `card`, `status`, `row`, `tab`, `chart`)
- **variant**: optional qualifier (`count`, `timestamp`, `duration`, `servers`, `tools`)

### Auto-Masked Suffixes (Visual Regression)

Suffixes that contain dynamic values should use these endings so visual regression tests can auto-mask them:

| Suffix | Meaning | Example |
|--------|---------|---------|
| `-count` | Numeric counter | `dashboard-requests-count` |
| `-timestamp` | Date/time value | `activity-last-updated-timestamp` |
| `-duration` | Duration value | `gateway-uptime-duration` |

## Current Inventory

### Console (control-plane-ui)

| Page | data-testid | Element |
|------|-------------|---------|
| Dashboard | `dashboard-title` | Page heading |
| Dashboard | `dashboard-kpi-grid` | KPI cards container |
| Dashboard | `dashboard-requests-count` | Requests StatCard |
| Dashboard | `dashboard-error-rate-count` | Error Rate StatCard |
| Dashboard | `dashboard-latency-count` | Latency P95 StatCard |
| Dashboard | `dashboard-gateways-count` | Gateways StatCard |
| Dashboard | `dashboard-traffic-chart` | Traffic sparkline section |
| Dashboard | `dashboard-error-chart` | Error sparkline section |
| Dashboard | `dashboard-gateway-instances` | Gateway instances list |
| Dashboard | `dashboard-top-apis` | Top APIs section |
| Tenants | `tenants-grid` | Tenant cards container |
| Tenants | `tenant-card` | Individual tenant card |
| Tenants | `tenant-name` | Tenant display name |
| Tenants | `tenant-status` | Tenant status badge |
| Gateways | `gateway-row` | Individual gateway row |
| Gateways | `gateway-status` | Gateway status badge |
| Gateways | `gateway-detail-overlay` | Detail panel overlay |
| Gateways | `gateway-detail-panel` | Detail slide-over panel |

### Portal

| Page | data-testid | Element |
|------|-------------|---------|
| Home | `home-header` | Welcome header + tenant badge |
| Home | `home-stats` | Dashboard stats cards |
| Home | `home-quick-actions` | Quick action buttons |
| Home | `home-featured` | Featured APIs + AI tools |
| Home | `home-activity` | Recent activity section |
| API Catalog | `catalog-results-count` | Results count text |
| API Catalog | `catalog-grid` | API cards grid |
| API Catalog | `catalog-pagination` | Pagination controls |
| Subscriptions | `subscriptions-stats` | Stats overview cards |
| Subscriptions | `subscriptions-active-count` | Active subs count |
| Subscriptions | `subscriptions-server-count` | Server subs count |
| Subscriptions | `subscriptions-usage-count` | Total API calls count |
| Subscriptions | `subscriptions-tab-servers` | Servers tab button |
| Subscriptions | `subscriptions-tab-tools` | Tools tab button |

## ARIA Roles Added

| Page | Element | Role/Attribute |
|------|---------|---------------|
| Dashboard | KPI grid | `role="region"` `aria-label="Platform KPIs"` |
| Tenants | Cards container | `role="list"` `aria-label="Tenants"` |
| Tenants | Individual card | `role="listitem"` |
| Gateways | Gateway list | `role="list"` `aria-label="<env> gateways"` |
| Gateways | Env tabs | `aria-label="Environment tabs"` (pre-existing) |
| API Catalog | API grid | `role="list"` `aria-label="API catalog"` |
| API Catalog | Pagination | `role="navigation"` `aria-label="Pagination"` |
| Subscriptions | Stats region | `role="region"` `aria-label="Subscription statistics"` |
| Subscriptions | Tabs | `role="tablist"` `aria-label="Subscription tabs"` |
| Subscriptions | Tab buttons | `role="tab"` `aria-selected` |
| StatCard (shared) | Card wrapper | `aria-label` (matches label prop) |

## Heading Hierarchy

All 6 audited pages follow correct heading hierarchy:
- `h1`: Page title (Dashboard, Tenants, Gateway Registry, API Catalog, My Subscriptions, Welcome)
- `h2`: Section headings (Traffic, Errors, Gateway Instances, Top APIs, environment names)
- `h3`: Card titles within sections (tenant names, gateway names)

No heading level skips (h1 -> h3) exist on audited pages.
