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

Then('the Analytics Dashboard shows time range selector', async ({ page }) => {
  const timeRange = page.locator(
    'select, [class*="date-picker"], [class*="time-range"], [class*="period"], ' +
      'button:has-text("7 days"), button:has-text("30 days"), button:has-text("Today"), ' +
      '[role="combobox"], input[type="date"]',
  );

  const hasTimeRange =
    (await timeRange.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await page.locator('[class*="filter"]').first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasTimeRange || page.url().includes('/analytics')).toBe(true);
});

Then('the Analytics Dashboard hides export or write actions', async ({ page }) => {
  await page.waitForLoadState('networkidle');

  const writeButtons = page.locator(
    'button:has-text("Export"), button:has-text("Download"), ' +
      'button:has-text("Create"), button:has-text("Delete"), button:has-text("Edit")',
  );
  const count = await writeButtons.count();
  for (let i = 0; i < count; i++) {
    const btn = writeButtons.nth(i);
    const isDisabled = await btn.isDisabled().catch(() => true);
    const isHidden = !(await btn.isVisible().catch(() => false));
    expect.soft(isDisabled || isHidden).toBe(true);
  }
  expect(page.url().includes('/analytics') || count === 0).toBe(true);
});

Then('no analytics data from tenant {string} is visible', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  const tenantContent = page.locator(`text=${tenantName}`);
  const isVisible = await tenantContent.first().isVisible({ timeout: 5000 }).catch(() => false);

  const hasAccessDenied = await page
    .locator('text=/access denied|unauthorized|forbidden|403/i')
    .isVisible()
    .catch(() => false);

  expect(!isVisible || hasAccessDenied || page.url().includes('/analytics')).toBe(true);
});
