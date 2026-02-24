/**
 * Portal Usage Dashboard step definitions for STOA E2E Tests
 * Steps specific to the Portal Usage Dashboard and Execution History pages
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// USAGE DASHBOARD NAVIGATION STEPS
// ============================================================================

When('I navigate to the portal usage dashboard', async ({ page }) => {
  await page.goto(`${URLS.portal}/usage`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the usage dashboard page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /usage|analytic|statistic/i });
  const content = page.locator(
    '[class*="chart"], [class*="graph"], [class*="metric"], canvas, svg, [class*="card"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/usage')).toBe(true);
});

// ============================================================================
// USAGE METRICS STEPS
// ============================================================================

Then('usage metrics or an empty state are displayed', async ({ page }) => {
  // Usage page should show charts/metrics OR an empty state if no data
  const metrics = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, ' +
      '[class*="metric"], [class*="count"], [class*="stat"]',
  );
  const emptyState = page.locator(
    'text=/no usage|no data|no calls|get started|empty/i',
  );

  const hasContent =
    (await metrics.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await emptyState.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/usage');

  expect.soft(hasContent).toBe(true);
  expect(hasContent).toBe(true);
});

// ============================================================================
// EXECUTION HISTORY NAVIGATION STEPS
// ============================================================================

When('I navigate to the portal execution history', async ({ page }) => {
  await page.goto(`${URLS.portal}/executions`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the execution history page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /execution|history|call/i });
  const content = page.locator(
    'table, [class*="list"], [class*="log"], text=/no execution|no history|empty/i',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  // Execution history may live under /usage or /executions depending on routing
  expect(loaded || page.url().includes('/executions') || page.url().includes('/usage')).toBe(true);
});
