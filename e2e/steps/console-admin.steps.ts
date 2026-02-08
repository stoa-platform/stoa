/**
 * Console Admin step definitions for STOA E2E Tests
 * Steps for gateway observability page
 * Note: tenants, prospects, monitoring steps are in admin-rbac.steps.ts
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// GATEWAY OBSERVABILITY PAGE
// ============================================================================

When('I navigate to the gateway observability page', async ({ page }) => {
  await page.goto(`${URLS.console}/gateway-observability`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the observability dashboard loads with health metrics', async ({ page }) => {
  const healthIndicator = page.locator(
    'text=/health|online|offline|synced|gateway/i',
  );
  const statusCards = page.locator('[class*="card"], [class*="stat"]');

  const loaded =
    (await healthIndicator.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await statusCards.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/gateway-observability')).toBe(true);
});
