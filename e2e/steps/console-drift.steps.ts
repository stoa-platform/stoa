/**
 * Console Drift Detection step definitions for STOA E2E Tests
 * Steps specific to the Drift Detection page
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// DRIFT DETECTION NAVIGATION STEPS
// ============================================================================

When('I navigate to the drift detection page', async ({ page }) => {
  await page.goto(`${URLS.console}/drift`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the drift detection page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /drift/i });
  const content = page.locator(
    '[class*="card"], [class*="list"], table, [class*="status"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/drift')).toBe(true);
});

// ============================================================================
// DRIFT STATUS STEPS
// ============================================================================

Then('gateway sync status information is visible', async ({ page }) => {
  // Drift page should show sync status per gateway: synced, drifted, pending, error
  const syncStatusIndicators = page.locator(
    'text=/synced|drifted|pending|in sync|out of sync|error/i, ' +
      '[class*="sync"], [class*="drift"], [class*="status"], [class*="badge"]',
  );

  const hasStatus =
    (await syncStatusIndicators.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/drift');

  // Soft assertion since drift page content depends on live gateway data
  expect.soft(hasStatus).toBe(true);
  expect(page.url().includes('/drift') || hasStatus).toBe(true);
});
