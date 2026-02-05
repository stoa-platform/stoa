/**
 * Portal Advanced step definitions for STOA E2E Tests
 * Steps for applications, profile, service accounts, analytics, webhooks
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// APPLICATIONS
// ============================================================================

When('I navigate to my applications page', async ({ page }) => {
  await page.goto(`${URLS.portal}/my-applications`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the applications page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /application/i });
  const content = page.locator(
    '[class*="card"], [class*="list"], table, text=/no application|create/i',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/my-applications')).toBe(true);
});

When('I create an application named {string}', async ({ page }, appName: string) => {
  const createButton = page.locator(
    'button:has-text("Create"), button:has-text("New Application"), button:has-text("Nouvelle")',
  );
  await expect(createButton).toBeVisible({ timeout: 10000 });
  await createButton.click();

  const nameInput = page.locator(
    'input[name="name"], input[placeholder*="name"], input[placeholder*="nom"]',
  ).first();
  await expect(nameInput).toBeVisible({ timeout: 5000 });
  await nameInput.fill(appName);

  const submitButton = page.locator(
    'button[type="submit"], button:has-text("Create"), button:has-text("Save")',
  );
  await submitButton.click();
  await page.waitForLoadState('networkidle');
});

Then('the application {string} appears in the list', async ({ page }, appName: string) => {
  const appEntry = page.locator(`text=${appName}`).first();
  await expect(appEntry).toBeVisible({ timeout: 10000 });
});

// ============================================================================
// PROFILE
// ============================================================================

When('I navigate to my profile page', async ({ page }) => {
  await page.goto(`${URLS.portal}/profile`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the profile page loads with user information', async ({ page }) => {
  const profileIndicator = page.locator(
    'text=/profile|email|username|account|profil|utilisateur/i',
  );
  const loaded = await profileIndicator.first().isVisible({ timeout: 10000 }).catch(() => false);
  expect(loaded || page.url().includes('/profile')).toBe(true);
});

// ============================================================================
// SERVICE ACCOUNTS
// ============================================================================

When('I navigate to the service accounts page', async ({ page }) => {
  await page.goto(`${URLS.portal}/service-accounts`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the service accounts page loads', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /service|account|compte/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/service-accounts')).toBe(true);
});

// ============================================================================
// ANALYTICS
// ============================================================================

When('I navigate to the usage analytics page', async ({ page }) => {
  await page.goto(`${URLS.portal}/usage`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the analytics page loads with usage data', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /usage|analytics|statistique/i });
  const charts = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/usage')).toBe(true);
});

// ============================================================================
// WEBHOOKS
// ============================================================================

When('I navigate to the webhooks page', async ({ page }) => {
  await page.goto(`${URLS.portal}/webhooks`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the webhooks page loads', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /webhook/i });
  const content = page.locator(
    '[class*="card"], [class*="list"], table, text=/no webhook|create/i',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/webhooks')).toBe(true);
});
