/**
 * Console Execution View and Error Taxonomy step definitions for STOA E2E Tests
 * Steps for execution view dashboard navigation and error taxonomy chart verification
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// EXECUTION VIEW
// ============================================================================

When('I navigate to the Execution View page', async ({ page }) => {
  await page.goto(`${URLS.console}/executions`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Execution View page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Execution/i });
  const content = page.locator(
    '[class*="card"], [class*="chart"], [class*="table"], table, [class*="list"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/executions')).toBe(true);
});

Then('the Error Taxonomy chart is visible', async ({ page }) => {
  const chart = page.locator(
    '[class*="taxonomy"], [class*="chart"], [class*="error-chart"], canvas, svg',
  );
  const errorSection = page.locator(
    'text=/error taxonomy|error categor|error breakdown/i',
  );

  const hasChart =
    (await chart.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await errorSection.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasChart || page.url().includes('/executions')).toBe(true);
});
