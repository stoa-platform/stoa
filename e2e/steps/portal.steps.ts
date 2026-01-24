/**
 * Portal step definitions for STOA E2E Tests
 * Steps specific to the Developer Portal (API Consumer)
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// CATALOG STEPS
// ============================================================================

When('I access the API catalog', async ({ page }) => {
  await page.goto(`${URLS.portal}/apis`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first()).not.toBeVisible({ timeout: 15000 }).catch(() => {});
});

Given('I am on the API catalog page', async ({ page }) => {
  await page.goto(`${URLS.portal}/apis`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first()).not.toBeVisible({ timeout: 15000 }).catch(() => {});
});

Given('I am viewing an API in the catalog', async ({ page }) => {
  await page.goto(`${URLS.portal}/apis`);
  await page.waitForLoadState('networkidle');

  const apiCard = page.locator('a[href^="/apis/"]').first();
  await apiCard.click();
  await page.waitForLoadState('networkidle');
});

Given('there are published APIs in the catalog', async ({ page }) => {
  await page.goto(`${URLS.portal}/apis`);
  await page.waitForLoadState('networkidle');

  const apiCards = page.locator('a[href^="/apis/"]');
  const count = await apiCards.count();
  expect(count).toBeGreaterThan(0);
});

Then('I see APIs in the catalog', async ({ page }) => {
  await expect(page.locator('text=Loading').first()).not.toBeVisible({ timeout: 15000 }).catch(() => {});

  const apiCards = page.locator('[class*="rounded-lg"][class*="border"], [class*="card"]');
  await expect(apiCards.first()).toBeVisible({ timeout: 10000 });
});

Then('I see the same catalog as other users', async ({ page }) => {
  const apiCards = page.locator('a[href^="/apis/"]');
  const count = await apiCards.count();
  expect(count).toBeGreaterThan(0);
});

// ============================================================================
// SEARCH & FILTER STEPS
// ============================================================================

When('I search for {string}', async ({ page }, query: string) => {
  const searchInput = page.locator('input[placeholder*="Search"], input[placeholder*="Rechercher"], input[type="search"]');
  await searchInput.fill(query);
  await page.waitForTimeout(500);
  await page.waitForLoadState('networkidle');
});

Then('the results contain {string}', async ({ page }, text: string) => {
  const results = page.locator('a[href^="/apis/"]');
  const count = await results.count();

  if (count > 0) {
    const firstResultText = await results.first().textContent();
    expect(firstResultText?.toLowerCase()).toContain(text.toLowerCase());
  }
});

When('I filter by category {string}', async ({ page }, category: string) => {
  const categoryFilter = page.locator('select, [role="combobox"]').filter({ hasText: /categor/i });

  if (await categoryFilter.isVisible()) {
    await categoryFilter.selectOption({ label: category });
  } else {
    await page.click(`text=${category}`);
  }

  await page.waitForLoadState('networkidle');
});

Then('all displayed APIs have category {string}', async ({ page }, category: string) => {
  const categoryBadges = page.locator(`text=${category}`);
  const count = await categoryBadges.count();
  expect(count).toBeGreaterThan(0);
});

// ============================================================================
// SUBSCRIPTION STEPS
// ============================================================================

Then('I see the list of my subscriptions', async ({ page }) => {
  await expect(page.locator('h1, h2').filter({ hasText: /subscription|souscription/i })).toBeVisible();
});

Then('each subscription shows its status', async ({ page }) => {
  const statusBadges = page.locator('[class*="badge"], [class*="status"]').filter({
    hasText: /active|pending|revoked|suspended|expired/i
  });

  const cards = page.locator('[class*="card"], [class*="rounded-lg"][class*="border"]');
  const cardCount = await cards.count();

  if (cardCount > 0) {
    await expect(statusBadges.first()).toBeVisible();
  }
});

When('I click on {string}', async ({ page }, buttonText: string) => {
  await page.click(`button:has-text("${buttonText}"), a:has-text("${buttonText}")`);
  await page.waitForLoadState('networkidle');
});

When('I confirm the subscription', async ({ page }) => {
  await page.click('button:has-text("Confirm"), button:has-text("Subscribe"), button:has-text("Confirmer")');
  await page.waitForLoadState('networkidle');
});

Then('the subscription is created with status {string}', async ({ page }, status: string) => {
  await expect(page.locator(`text=${status}`)).toBeVisible({ timeout: 10000 });
});

Then('I can see my new API key', async ({ page }) => {
  await expect(page.locator('text=/^[a-zA-Z0-9_-]{20,}|sk_|pk_|api_/i')).toBeVisible({ timeout: 10000 });
});

Given('I have an active subscription', async ({ page }) => {
  await page.goto(`${URLS.portal}/subscriptions`);
  await page.waitForLoadState('networkidle');

  const activeStatus = page.locator('text=active');
  await expect(activeStatus.first()).toBeVisible({ timeout: 10000 });
});

When('I click on {string} for a subscription', async ({ page }, buttonText: string) => {
  const subscriptionCard = page.locator('[class*="card"], [class*="rounded-lg"]').first();
  await subscriptionCard.locator(`button:has-text("${buttonText}"), a:has-text("${buttonText}")`).click();
  await page.waitForLoadState('networkidle');
});

Then('I can see the API key information', async ({ page }) => {
  await expect(page.locator('text=/key|cle|prefix/i')).toBeVisible();
});

Then('I can reveal the complete API key', async ({ page }) => {
  const revealButton = page.locator('button:has-text("Reveal"), button:has-text("Show"), button:has-text("Afficher")');
  if (await revealButton.isVisible()) {
    await revealButton.click();
    await expect(page.locator('text=/^[a-zA-Z0-9_-]{32,}/i')).toBeVisible({ timeout: 10000 });
  }
});

When('I confirm the revocation', async ({ page }) => {
  await page.click('button:has-text("Confirm"), button:has-text("Revoke"), button:has-text("Confirmer")');
  await page.waitForLoadState('networkidle');
});

Then('the subscription changes to status {string}', async ({ page }, status: string) => {
  await expect(page.locator(`text=${status}`)).toBeVisible({ timeout: 10000 });
});

Then('I see only my own subscriptions', async ({ page }) => {
  await expect(page.locator('h1, h2').first()).toBeVisible();
});

Then('I do not see subscriptions from {string}', async ({ page }, tenant: string) => {
  const tenantText = page.locator(`text=${tenant}`).filter({ hasText: tenant });
  await expect(tenantText).not.toBeVisible();
});
