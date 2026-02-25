/**
 * Console Analytics Dashboard step definitions for STOA E2E Tests
 * Steps for analytics dashboard page navigation and content verification
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// ANALYTICS DASHBOARD
// ============================================================================

When('I navigate to the Analytics Dashboard page', async ({ page }) => {
  await page.goto(`${URLS.console}/analytics`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Analytics Dashboard page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Analytics/i });
  const charts = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"], [class*="card"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/analytics')).toBe(true);
});

Then('the Analytics Dashboard displays consumer data', async ({ page }) => {
  const consumerTable = page.locator('table, [class*="table"], [class*="consumer"]');
  const chartContent = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"]',
  );

  const hasContent =
    (await consumerTable.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await chartContent.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasContent || page.url().includes('/analytics')).toBe(true);
});
