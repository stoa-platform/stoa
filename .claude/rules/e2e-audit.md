# E2E Audit Standard

> Mandatory protocol for any E2E audit session (subscription, dashboard, security, performance).
> Every audit produces a **self-contained directory** that someone can read in 2 weeks and understand exactly what was done.

## Audit Directory Structure

```
docs/audits/YYYY-MM-DD-<topic>/
├── .gitignore             # Excludes videos from git
├── README.md              # Structured report (template below)
├── results.json           # Playwright JSON results (machine-readable)
├── report/                # Playwright HTML report
│   ├── index.html         # Open in browser — shows screenshots + videos inline
│   └── data/
│       ├── *.png          # Screenshots (committed)
│       └── *.webm         # Videos (gitignored, local only)
└── videos/                # Videos with readable names (gitignored, local only)
    └── <test-name>.webm
```

**Naming**: `YYYY-MM-DD-<kebab-case-topic>`. Examples: `2026-04-04-subscription-dashboard`, `2026-05-15-gateway-security`.

## Report Template (README.md)

Every audit README.md MUST have these sections in this order:

```markdown
# Audit: <Title>

**Date**: YYYY-MM-DD
**Author**: <who ran this>
**Ticket**: CAB-XXXX or N/A
**PR**: #NNNN
**Duration**: ~Xh

## Scope
What was tested and why. 1-3 sentences.

## Results
**N tests, M skipped, K failed** (duration)

### Coverage Matrix
Table mapping what was tested × what was verified.

### Dashboard/UI Verification
Table: Dashboard | Data Source | Real Data Visible | Evidence (screenshot name)

## Bugs Found & Fixed
Table: # | Severity | Component | Issue | Fix

## Architecture Findings
Non-obvious discoveries about the system design.

## Test File
Path + run command + prerequisites.

## Screenshots
List of trace screenshots with what each shows.
Re-generated on every test run (not committed).
```

## Test File Standard

Audit Playwright tests go in `e2e/tests/local-<topic>.spec.ts` and follow this structure:

```typescript
// Phase A — Setup & Data Creation (API calls, no browser)
// Phase B — Console UI Traces (login + navigate + screenshot each dashboard)
// Phase C — Portal UI Traces (login + navigate + screenshot each page)
// Phase D — Cross-validation & Lifecycle (API assertions, isolation, cleanup)
```

### Rules

1. **No skips** — if something can't be tested, fix the blocker first, then test
2. **No fake data** — all dashboard values must come from actions in earlier phases
3. **Screenshots are assertions** — take `fullPage: true` screenshots AFTER data is visible, name them `trace-<app>-<page>.png`
4. **Cross-validate** — Phase D must query the API and assert that counts match what was created in earlier phases
5. **Loki integration** — if the feature involves call logs, push structured logs to Loki and verify "Recent Calls" shows them
6. **Idempotent** — tests must be runnable multiple times without cleanup. Use timestamps in names, handle 409 (already exists)

## Generating the Report

After tests pass, archive the report into the audit directory:

```bash
# 1. Run tests
cd e2e && npx playwright test --config playwright.local.config.ts tests/local-<topic>.spec.ts

# 2. Copy HTML report to audit dir
AUDIT_DIR=docs/audits/YYYY-MM-DD-<topic>
mkdir -p "$AUDIT_DIR/report"
cp -r reports/local/* "$AUDIT_DIR/report/"
cp reports/local/results.json "$AUDIT_DIR/results.json"

# 3. Commit
git add "$AUDIT_DIR" e2e/tests/local-<topic>.spec.ts
git commit -m "docs(e2e): <topic> audit report + tests"
```

## What to Commit

| Artifact | Committed | Why |
|----------|-----------|-----|
| `docs/audits/<date>-<topic>/README.md` | **Yes** | Permanent record |
| `docs/audits/<date>-<topic>/report/index.html` | **Yes** | Self-contained HTML report |
| `docs/audits/<date>-<topic>/report/data/*.png` | **Yes** | Screenshots (evidence) |
| `docs/audits/<date>-<topic>/results.json` | **Yes** | Machine-readable results |
| `docs/audits/<date>-<topic>/.gitignore` | **Yes** | Excludes videos from git |
| `e2e/tests/local-<topic>.spec.ts` | **Yes** | Reproducible tests |
| `docs/audits/<date>-<topic>/videos/*.webm` | **No** (gitignored) | Local only — re-generate with test run |
| `docs/audits/<date>-<topic>/report/data/*.webm` | **No** (gitignored) | Same videos referenced by HTML report |

### .gitignore template for audit directories

```
# Videos kept locally, not committed (too heavy for git)
# Re-generate: cd e2e && npx playwright test --config playwright.local.config.ts tests/local-<topic>.spec.ts
videos/
report/data/*.webm
```

### Viewing videos locally

After running tests, videos are in two places:
- `videos/<test-name>.webm` — named for easy browsing
- `report/data/<hash>.webm` — referenced by `report/index.html`

Open `report/index.html` in a browser to see screenshots + videos inline with test results.

## Observability Stack (for dashboard audits)

If the audit involves verifying dashboards that read from Prometheus or Loki:

1. **Prometheus**: ensure `stoa-prometheus` scrapes the gateway (`host.docker.internal:30080`)
2. **Loki**: ensure `stoa-loki` is running, push logs with correct `user_id` and `tenant_id` stream labels
3. **API env**: `PROMETHEUS_INTERNAL_URL=http://stoa-prometheus:9090`, `LOKI_INTERNAL_URL=http://stoa-loki:3100`

### Loki Log Format

```json
{
  "stream": {
    "job": "stoa-gateway",
    "user_id": "<email — matches current_user.id fallback>",
    "tenant_id": "default",
    "service": "stoa-gateway"
  },
  "values": [
    ["<timestamp_ns>", "{\"request_id\":\"...\",\"tool_name\":\"...\",\"status\":\"success|error|timeout\",\"duration_ms\":123}"]
  ]
}
```

**Note**: The API uses `email` as `user_id` (not UUID) because the KC `sub` claim is missing from `control-plane-ui` tokens. Match accordingly.

## When to Run an Audit

- New feature touching subscriptions, dashboards, or observability
- After Prometheus/Loki metric changes
- After gateway auth flow changes
- Quarterly health check on the subscription pipeline
