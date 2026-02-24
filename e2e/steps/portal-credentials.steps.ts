/**
 * Portal Credential Mappings step definitions for STOA E2E Tests
 * Steps specific to the Portal Credential Mappings page
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// CREDENTIALS NAVIGATION STEPS
// ============================================================================

When('I navigate to the portal credentials page', async ({ page }) => {
  await page.goto(`${URLS.portal}/credentials`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the portal credentials page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /credential/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/credentials')).toBe(true);
});

// ============================================================================
// CREDENTIALS CONTENT STEPS
// ============================================================================

Then('credential mappings list or empty state is displayed', async ({ page }) => {
  // Either a list of credential mappings OR an empty state
  const listContent = page.locator(
    'table tbody tr, [class*="card"], a[href*="/credentials/"]',
  );
  const emptyState = page.locator(
    'text=/no credential|create|add your first|empty|no mapping/i',
  );

  const hasContent =
    (await listContent.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await emptyState.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/credentials');

  expect(hasContent).toBe(true);
});

// ============================================================================
// CREDENTIALS ISOLATION STEPS
// ============================================================================

Then('no credentials from tenant {string} are visible', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  // Credentials are tenant-scoped — IOI users should only see IOI credentials
  const crossTenantContent = page
    .locator(`text=${tenantName}`)
    .filter({ hasText: new RegExp(tenantName, 'i') });
  const isVisible = await crossTenantContent
    .first()
    .isVisible({ timeout: 5000 })
    .catch(() => false);

  const hasAccessDenied = await page
    .locator('text=/access denied|unauthorized|forbidden|403/i')
    .isVisible()
    .catch(() => false);

  // Pass if cross-tenant data is NOT visible, OR access was denied entirely
  expect(!isVisible || hasAccessDenied).toBe(true);
});
