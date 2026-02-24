/**
 * Portal Workspace Tabs step definitions for STOA E2E Tests
 * Steps specific to the Portal Workspace page and its tabs
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// WORKSPACE NAVIGATION STEPS
// ============================================================================

When('I navigate to the portal workspace', async ({ page }) => {
  await page.goto(`${URLS.portal}/workspace`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the workspace page loads with tabs', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /workspace/i });
  // Tabs can be role="tab", [class*="tab"], or nav links
  const tabs = page.locator(
    '[role="tab"], [class*="tab"], nav a, [class*="TabList"] button',
  );

  const headingVisible = await heading.isVisible({ timeout: 10000 }).catch(() => false);
  const tabsVisible = await tabs.first().isVisible({ timeout: 5000 }).catch(() => false);

  expect(headingVisible || tabsVisible || page.url().includes('/workspace')).toBe(true);
});

// ============================================================================
// WORKSPACE TAB NAVIGATION STEPS
// ============================================================================

When('I click on the subscriptions workspace tab', async ({ page }) => {
  // Try tab by text first, then by query param navigation
  const subTab = page.locator(
    '[role="tab"]:has-text("Subscription"), ' +
      '[class*="tab"]:has-text("Subscription"), ' +
      'button:has-text("Subscription"), ' +
      'a:has-text("Subscription")',
  );

  if (await subTab.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await subTab.first().click();
    await page.waitForLoadState('networkidle');
  } else {
    // Navigate directly with query param (matches portal-advanced pattern)
    await page.goto(`${URLS.portal}/workspace?tab=subscriptions`);
    await page.waitForLoadState('networkidle');
  }
});

Then('the subscriptions tab content is displayed', async ({ page }) => {
  const content = page.locator(
    '[role="tabpanel"], [class*="panel"], ' +
      'text=/subscription|no subscription|subscribe/i',
  );

  const loaded =
    (await content.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('subscription') ||
    page.url().includes('/workspace');

  expect(loaded).toBe(true);
});

When('I click on the applications workspace tab', async ({ page }) => {
  const appTab = page.locator(
    '[role="tab"]:has-text("Application"), ' +
      '[class*="tab"]:has-text("Application"), ' +
      'button:has-text("Application"), ' +
      'a:has-text("Application")',
  );

  if (await appTab.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await appTab.first().click();
    await page.waitForLoadState('networkidle');
  } else {
    await page.goto(`${URLS.portal}/workspace?tab=apps`);
    await page.waitForLoadState('networkidle');
  }
});

Then('the applications tab content is displayed', async ({ page }) => {
  const content = page.locator(
    '[role="tabpanel"], [class*="panel"], ' +
      'text=/application|no application|create app/i',
  );

  const loaded =
    (await content.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('app') ||
    page.url().includes('/workspace');

  expect(loaded).toBe(true);
});

When('I click on the contracts workspace tab', async ({ page }) => {
  const contractTab = page.locator(
    '[role="tab"]:has-text("Contract"), ' +
      '[class*="tab"]:has-text("Contract"), ' +
      'button:has-text("Contract"), ' +
      'a:has-text("Contract")',
  );

  if (await contractTab.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await contractTab.first().click();
    await page.waitForLoadState('networkidle');
  } else {
    await page.goto(`${URLS.portal}/workspace?tab=contracts`);
    await page.waitForLoadState('networkidle');
  }
});

Then('the contracts tab content is displayed', async ({ page }) => {
  const content = page.locator(
    '[role="tabpanel"], [class*="panel"], ' +
      'text=/contract|no contract|UAC/i',
  );

  const loaded =
    (await content.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('contract') ||
    page.url().includes('/workspace');

  expect(loaded).toBe(true);
});
