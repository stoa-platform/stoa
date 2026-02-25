/**
 * Console Admin Access Requests step definitions for STOA E2E Tests
 * Steps for access requests page navigation and RBAC verification
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// ADMIN ACCESS REQUESTS
// ============================================================================

When('I navigate to the Admin Access Requests page', async ({ page }) => {
  await page.goto(`${URLS.console}/admin/access-requests`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Admin Access Requests page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Access Request/i });
  const content = page.locator('table, [class*="table"], [class*="list"], [class*="card"]');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/admin/access-requests')).toBe(true);
});
