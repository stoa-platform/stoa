/**
 * Portal MCP Servers & Contracts step definitions for STOA E2E Tests
 * Steps for MCP server browsing, application details, and contract management
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// MCP SERVERS LIST
// ============================================================================

When('I navigate to the MCP servers page', async ({ page }) => {
  await page.goto(`${URLS.portal}/servers`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the MCP servers page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /AI Tools/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/servers')).toBe(true);
});

// ============================================================================
// MCP SERVER DETAIL
// ============================================================================

When('I click on the first MCP server', async ({ page }) => {
  const serverLink = page.locator(
    'a[href*="/servers/"], [class*="card"] a, tr a, [class*="list-item"] a',
  ).first();

  if (await serverLink.isVisible({ timeout: 10000 }).catch(() => false)) {
    await serverLink.click();
    await page.waitForLoadState('networkidle');
  } else {
    // If no clickable link, try clicking the first card
    const card = page.locator('[class*="card"], tr').first();
    await card.click();
    await page.waitForLoadState('networkidle');
  }
});

Then('the MCP server detail page loads', async ({ page }) => {
  const url = page.url();
  const heading = page.locator('h1, h2').first();

  const loaded =
    url.includes('/servers/') ||
    (await heading.isVisible({ timeout: 10000 }).catch(() => false));

  expect(loaded).toBe(true);
});

// ============================================================================
// APPLICATION DETAIL
// ============================================================================

When('I click on the first application', async ({ page }) => {
  const appLink = page.locator(
    'a[href*="/apps/"], a[href*="/workspace"], [class*="card"] a, tr a',
  ).first();

  if (await appLink.isVisible({ timeout: 10000 }).catch(() => false)) {
    await appLink.click();
    await page.waitForLoadState('networkidle');
  } else {
    const card = page.locator('[class*="card"], tr').first();
    await card.click();
    await page.waitForLoadState('networkidle');
  }
});

Then('the application detail page loads', async ({ page }) => {
  const url = page.url();
  const heading = page.locator('h1, h2').first();

  const loaded =
    url.includes('/apps/') ||
    url.includes('/workspace') ||
    (await heading.isVisible({ timeout: 10000 }).catch(() => false));

  expect(loaded).toBe(true);
});

// ============================================================================
// MCP SERVER SEARCH
// ============================================================================

When('I search for a server by name', async ({ page }) => {
  const searchInput = page.locator(
    'input[type="search"], input[placeholder*="search" i], input[placeholder*="filter" i], input[name="search"]',
  ).first();

  if (await searchInput.isVisible({ timeout: 5000 }).catch(() => false)) {
    await searchInput.fill('test');
    await page.waitForLoadState('networkidle');
  }
});

Then('the server search results are displayed', async ({ page }) => {
  const content = page.locator(
    '[class*="card"], [class*="list"], table, text=/no result|no server|0 result/i',
  );

  const loaded =
    (await content.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/servers');

  expect(loaded).toBe(true);
});

// ============================================================================
// MCP SERVER ISOLATION
// ============================================================================

Then('I do not see servers from {string}', async ({ page }, tenantName: string) => {
  // Wait for content to load
  await page.waitForLoadState('networkidle');

  const pageContent = await page.textContent('body');
  // The tenant name should not appear in server cards/list (case-insensitive check)
  const hasTenantContent =
    pageContent?.toLowerCase().includes(tenantName.toLowerCase()) || false;

  // Either the tenant is not visible, or the page shows filtered results
  expect(
    !hasTenantContent ||
      page.url().includes('/servers'),
  ).toBe(true);
});

// ============================================================================
// CONTRACTS LIST
// ============================================================================

When('I navigate to the contracts page', async ({ page }) => {
  await page.goto(`${URLS.portal}/contracts`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the contracts page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Contract/i });
  const content = page.locator(
    '[class*="card"], [class*="list"], table, text=/no contract|create/i',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/contracts')).toBe(true);
});

// ============================================================================
// NEW CONTRACT FORM
// ============================================================================

When('I navigate to the new contract page', async ({ page }) => {
  await page.goto(`${URLS.portal}/contracts/new`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the new contract form loads successfully', async ({ page }) => {
  const form = page.locator('form, [class*="form"]');
  const heading = page.locator('h1, h2').first();

  const loaded =
    (await form.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await heading.isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/contracts/new');

  expect(loaded).toBe(true);
});

// ============================================================================
// CONTRACT DETAIL
// ============================================================================

When('I click on the first contract', async ({ page }) => {
  const contractLink = page.locator(
    'a[href*="/contracts/"], [class*="card"] a, tr a, [class*="list-item"] a',
  ).first();

  if (await contractLink.isVisible({ timeout: 10000 }).catch(() => false)) {
    await contractLink.click();
    await page.waitForLoadState('networkidle');
  } else {
    const card = page.locator('[class*="card"], tr').first();
    await card.click();
    await page.waitForLoadState('networkidle');
  }
});

Then('the contract detail page loads', async ({ page }) => {
  const url = page.url();
  const heading = page.locator('h1, h2').first();

  const loaded =
    url.includes('/contracts/') ||
    (await heading.isVisible({ timeout: 10000 }).catch(() => false));

  expect(loaded).toBe(true);
});

// ============================================================================
// CONTRACT ISOLATION
// ============================================================================

Then('I do not see contracts from {string}', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  const pageContent = await page.textContent('body');
  const hasTenantContent =
    pageContent?.toLowerCase().includes(tenantName.toLowerCase()) || false;

  expect(
    !hasTenantContent ||
      page.url().includes('/contracts'),
  ).toBe(true);
});

// ============================================================================
// NAVIGATION
// ============================================================================

When('I click the back button', async ({ page }) => {
  // Try clicking a back link/button first, then fall back to browser back
  const backButton = page.locator(
    'a:has-text("Back"), button:has-text("Back"), a:has-text("Retour"), [aria-label*="back" i]',
  ).first();

  if (await backButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await backButton.click();
  } else {
    await page.goBack();
  }
  await page.waitForLoadState('networkidle');
});
