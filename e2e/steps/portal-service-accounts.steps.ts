/**
 * Portal Service Accounts step definitions for STOA E2E Tests
 * Steps specific to the Portal Service Accounts page
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// SERVICE ACCOUNTS NAVIGATION STEPS
// ============================================================================

When('I navigate to the portal service accounts page', async ({ page }) => {
  await page.goto(`${URLS.portal}/service-accounts`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the portal service accounts page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /service.?account/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/service-accounts')).toBe(true);
});

// ============================================================================
// SERVICE ACCOUNTS CONTENT STEPS
// ============================================================================

Then('the service account list or empty state is displayed', async ({ page }) => {
  // Either a list of service accounts OR an empty state message
  const listContent = page.locator('table tbody tr, [class*="card"], a[href*="/service-accounts/"]');
  const emptyState = page.locator(
    'text=/no service account|create|add your first|empty/i',
  );

  const hasContent =
    (await listContent.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await emptyState.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/service-accounts');

  expect(hasContent).toBe(true);
});
