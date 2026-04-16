# AI-Verified UI Validation — Runbook

Operational guide for the 4-layer UI validation framework delivered in CAB-1989.

## Purpose

Let an LLM (Claude Code, Cursor, Devin) verify UI correctness without parsing screenshots. Screenshots show pixels; AI cannot reliably assert "the dashboard displays 3 gateways" from an image. The framework replaces that with structured, parseable assertions.

## Layers

| Layer | Fixture / tool | Asserts |
|-------|----------------|---------|
| Data seeding | `e2e/fixtures/data-seeder.ts` | Known entities exist via Control Plane API |
| ARIA snapshots | `e2e/fixtures/aria-helpers.ts` | Table rows, metric values, no empty states |
| Cross-validation | `e2e/tests/cross-validation/*` | API data == UI data on 3 critical pages |
| A11y gate | `e2e/fixtures/a11y.ts` + CI | Zero critical + serious WCAG 2.1 AA violations |

Visual regression (Docker golden baselines) deferred to a follow-up ticket.

## How to add a cross-validation spec

```ts
import { test } from '../../fixtures/seeded-test';
import { assertTableHasRows, assertNoEmptyStates } from '../../fixtures/aria-helpers';

test('my page renders seeded data', async ({ seeded, page }) => {
  const api = await seeded.createApi({ name: 'canary-api-1' });
  await page.goto('/catalog');
  await assertTableHasRows(page, 'catalog-grid', 1);
  await assertNoEmptyStates(page);
});
```

`seeded` auto-creates + cleans up on teardown. Name entities with a session prefix so a stuck cleanup never collides with real data.

## How to add an a11y gate

```ts
import { assertNoA11yViolations } from '../../fixtures/a11y';

test('dashboard meets WCAG 2.1 AA', async ({ page }, testInfo) => {
  await page.goto('/dashboard');
  await assertNoA11yViolations(page, testInfo);
});
```

Default level blocks **critical + serious**. `moderate` and `minor` surface as annotations on the test report but do not fail CI.

## Local metrics snapshot

```bash
scripts/e2e/measure-ai-ui-validation.sh          # human-readable
scripts/e2e/measure-ai-ui-validation.sh --json   # for CI consumption
```

## Convention: `data-testid`

See `docs/e2e/data-testid-convention.md`. Ratchet only — add a testid when a spec needs it, not big-bang.

## CI

- `.github/workflows/e2e-a11y-gate.yml` runs the `a11y` Playwright project on every touch to `e2e/fixtures/a11y.ts`, `e2e/tests/a11y/**`, or the Console/Portal source.
- Cross-validation specs run as part of the main E2E workflow.

## Follow-ups

- Visual regression (`toHaveScreenshot()` Docker) — separate ticket, deferred from CAB-1989 MVP.
- ADR-061 (`stoa-docs/docs/architecture/adr/`) — formalises the 4-layer model for external contributors.
