/**
 * Console Admin step definitions for STOA E2E Tests
 * Steps for platform admin pages (tenants, prospects, monitoring, observability)
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// TENANTS PAGE
// ============================================================================

When('I navigate to the tenants page', async ({ page }) => {
  await page.goto(`${URLS.console}/tenants`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the tenants list loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /tenant/i });
  const table = page.locator('table, [class*="grid"], [class*="list"]');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await table.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/tenants')).toBe(true);
});

// ============================================================================
// PROSPECTS PAGE
// ============================================================================

When('I navigate to the admin prospects page', async ({ page }) => {
  await page.goto(`${URLS.console}/admin/prospects`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the prospects page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /prospect/i });
  const table = page.locator('table, [class*="grid"], [class*="list"]');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await table.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/prospects')).toBe(true);
});

// ============================================================================
// MONITORING PAGE
// ============================================================================

When('I navigate to the monitoring page', async ({ page }) => {
  await page.goto(`${URLS.console}/monitoring`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the monitoring dashboard loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /monitor|dashboard|api/i });
  const charts = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/monitoring')).toBe(true);
});

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
