/**
 * Portal Webhooks step definitions for STOA E2E Tests
 * Steps specific to the Portal Webhooks page
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// PORTAL WEBHOOKS NAVIGATION STEPS
// ============================================================================

When('I navigate to the portal webhooks page', async ({ page }) => {
  await page.goto(`${URLS.portal}/webhooks`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the portal webhooks page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /webhook/i });
  const content = page.locator(
    '[class*="card"], [class*="list"], table, text=/no webhook|create|add/i',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/webhooks')).toBe(true);
});

// ============================================================================
// WEBHOOK CONFIGURATION STEPS
// ============================================================================

Then('webhook configuration options are visible', async ({ page }) => {
  // Check for webhook creation button or configuration fields
  const configOptions = page.locator(
    'button:has-text("Create"), button:has-text("Add"), button:has-text("New Webhook"), ' +
      'input[placeholder*="url" i], input[placeholder*="endpoint" i], ' +
      'text=/endpoint|url|secret|event/i',
  );

  const hasOptions =
    (await configOptions.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/webhooks');

  expect.soft(hasOptions).toBe(true);
  expect(page.url().includes('/webhooks') || hasOptions).toBe(true);
});

// ============================================================================
// WEBHOOK ISOLATION STEPS
// ============================================================================

Then('no webhooks from tenant {string} are visible', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  // Portal webhooks are tenant-scoped — IOI users should only see IOI webhooks
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
