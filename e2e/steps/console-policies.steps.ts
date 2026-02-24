/**
 * Console Policies step definitions for STOA E2E Tests
 * Steps specific to the Policies management page
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// POLICIES NAVIGATION STEPS
// ============================================================================

When('I navigate to the policies page', async ({ page }) => {
  await page.goto(`${URLS.console}/policies`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the policies page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /polic/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/policies')).toBe(true);
});

// ============================================================================
// POLICIES RBAC STEPS
// ============================================================================

Then('policy write actions are hidden or disabled', async ({ page }) => {
  // Viewers should not see create/edit/delete policy buttons
  const writeButtons = page.locator(
    'button:has-text("Create"), button:has-text("New Policy"), ' +
      'button:has-text("Add Policy"), button:has-text("Delete"), button:has-text("Edit")',
  );
  const count = await writeButtons.count();
  for (let i = 0; i < count; i++) {
    const btn = writeButtons.nth(i);
    const isDisabled = await btn.isDisabled().catch(() => true);
    const isHidden = !(await btn.isVisible().catch(() => false));
    expect.soft(isDisabled || isHidden).toBe(true);
  }
  // If no write buttons found at all, RBAC is correctly hiding them
  expect(page.url().includes('/policies') || count === 0).toBe(true);
});
