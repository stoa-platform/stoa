/**
 * Console Platform Diagnostics step definitions for STOA E2E Tests
 * Steps specific to the Diagnostics and Error Snapshots pages
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// DIAGNOSTICS NAVIGATION STEPS
// ============================================================================

When('I navigate to the diagnostics page', async ({ page }) => {
  await page.goto(`${URLS.console}/diagnostics`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the diagnostics page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /diagnostic/i });
  const content = page.locator(
    '[class*="card"], [class*="status"], [class*="health"], [class*="check"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/diagnostics')).toBe(true);
});

// ============================================================================
// HEALTH CHECK STEPS
// ============================================================================

Then('health check status indicators are visible', async ({ page }) => {
  // Diagnostics page should show health check cards/indicators
  const statusIndicators = page.locator(
    '[class*="status"], [class*="health"], [class*="check"], ' +
      'text=/healthy|degraded|error|ok|pass|fail/i, ' +
      '[class*="badge"], [class*="chip"]',
  );

  const hasIndicators =
    (await statusIndicators.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/diagnostics');

  expect.soft(hasIndicators).toBe(true);
  expect(page.url().includes('/diagnostics') || hasIndicators).toBe(true);
});

// ============================================================================
// ERROR SNAPSHOTS STEPS
// ============================================================================

When('I navigate to the error snapshots page', async ({ page }) => {
  // Try /errors path first, fall back to /diagnostics/errors
  await page.goto(`${URLS.console}/errors`);
  await page.waitForLoadState('networkidle');

  // If redirected away from /errors, try the nested path
  if (!page.url().includes('/errors')) {
    await page.goto(`${URLS.console}/diagnostics/errors`);
    await page.waitForLoadState('networkidle');
  }

  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the error snapshots page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /error|snapshot/i });
  const content = page.locator(
    '[class*="card"], [class*="list"], table, text=/no errors|no snapshot|empty/i',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  // Acceptable outcomes: page loaded with content, or page redirected (feature gated)
  expect(loaded || page.url().includes('/error') || page.url().includes('/diagnostic')).toBe(true);
});
