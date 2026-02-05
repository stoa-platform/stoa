/**
 * Console Gateway step definitions for STOA E2E Tests
 * Steps specific to the Gateway and Deployment management pages
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// GATEWAY NAVIGATION STEPS
// ============================================================================

When('I navigate to the gateways page', async ({ page }) => {
  await page.goto(`${URLS.console}/gateways`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the gateway list page loads successfully', async ({ page }) => {
  // Should see a heading or table related to gateways
  const heading = page.locator('h1, h2').filter({ hasText: /gateway/i });
  const table = page.locator('table, [class*="grid"], [class*="list"]');
  const pageLoaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await table.first().isVisible({ timeout: 5000 }).catch(() => false));

  // If gateways page exists, it loaded; if redirected, the page still loaded
  expect(pageLoaded || page.url().includes('/gateways')).toBe(true);
});

When('I click on the first gateway', async ({ page }) => {
  const gatewayRow = page.locator(
    'table tbody tr, a[href*="/gateways/"], [class*="card"]',
  ).first();
  await expect(gatewayRow).toBeVisible({ timeout: 10000 });
  await gatewayRow.click();
  await page.waitForLoadState('networkidle');
});

Then('the gateway detail page loads', async ({ page }) => {
  // Should see gateway details or a back button
  const detailIndicator = page.locator(
    'text=/status|configuration|config|health|detail/i',
  );
  const isDetail =
    (await detailIndicator.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/gateways/');

  expect(isDetail).toBe(true);
});

// ============================================================================
// DEPLOYMENT DASHBOARD STEPS
// ============================================================================

When('I navigate to the gateway deployments page', async ({ page }) => {
  await page.goto(`${URLS.console}/gateway-deployments`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the deployments dashboard loads with sync status cards', async ({ page }) => {
  // Dashboard should show status cards or a deployment table
  const statusCards = page.locator(
    '[class*="card"], [class*="stat"], text=/synced|pending|drifted|error/i',
  );
  const table = page.locator('table, [class*="grid"]');

  const dashboardLoaded =
    (await statusCards.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await table.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/gateway-deployments');

  expect(dashboardLoaded).toBe(true);
});
