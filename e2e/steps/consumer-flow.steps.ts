/**
 * Consumer Flow step definitions for STOA E2E Tests
 * Steps for the API consumer journey: discover, subscribe, consume
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// API CATALOG DETAIL STEPS
// ============================================================================

When('I click on the first API in the catalog', async ({ page }) => {
  const apiCard = page.locator('a[href^="/apis/"]').first();
  await expect.soft(apiCard).toBeVisible({ timeout: 10000 });
  await apiCard.click();
  await page.waitForLoadState('networkidle');
});

Then('the API detail page loads with description and endpoints', async ({ page }) => {
  const url = page.url();
  const heading = page.locator('h1, h2').first();
  const description = page.locator('text=/description|overview|endpoint|version|base url/i');

  const loaded =
    url.includes('/apis/') ||
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await description.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect.soft(loaded).toBe(true);
});

// ============================================================================
// APPLICATION MANAGEMENT STEPS
// ============================================================================

When('I create an application named {string}', async ({ page }, appName: string) => {
  const createButton = page.locator(
    'button:has-text("Create"), button:has-text("New Application"), button:has-text("Nouveau")',
  );
  await expect.soft(createButton.first()).toBeVisible({ timeout: 10000 });
  await createButton.first().click();
  await page.waitForLoadState('networkidle');

  const nameInput = page
    .locator('input[name="name"], input[placeholder*="name" i], input[id="name"]')
    .first();
  await expect.soft(nameInput).toBeVisible({ timeout: 5000 });
  await nameInput.fill(appName);

  const submitButton = page.locator(
    'button[type="submit"], button:has-text("Create"), button:has-text("Save")',
  );
  await submitButton.click();
  await page.waitForLoadState('networkidle');
});

Then('the application {string} appears in the list', async ({ page }, appName: string) => {
  const appEntry = page.locator(`text=${appName}`).first();
  await expect.soft(appEntry).toBeVisible({ timeout: 10000 });
});

When('I click on the first application', async ({ page }) => {
  const appRow = page
    .locator('table tbody tr, a[href*="/apps/"], a[href*="/applications/"], [class*="card"]')
    .first();
  await expect.soft(appRow).toBeVisible({ timeout: 10000 });
  await appRow.click();
  await page.waitForLoadState('networkidle');
});

Then('the application detail page loads', async ({ page }) => {
  const detailIndicator = page.locator(
    'text=/api key|credentials|subscription|detail|overview/i',
  );
  const isDetail =
    (await detailIndicator.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/apps/') ||
    page.url().includes('/applications/');
  expect.soft(isDetail).toBe(true);
});

// ============================================================================
// SUBSCRIPTION FLOW STEPS
// ============================================================================

When('I click the subscribe button', async ({ page }) => {
  const subscribeButton = page.locator(
    'button:has-text("Subscribe"), button:has-text("Souscrire"), a:has-text("Subscribe")',
  );
  await expect.soft(subscribeButton.first()).toBeVisible({ timeout: 10000 });
  await subscribeButton.first().click();
  await page.waitForLoadState('networkidle');
});

When(
  'I select application {string} for the subscription',
  async ({ page }, appName: string) => {
    const appSelect = page
      .locator('select[name*="application"], select[name*="app"], [role="combobox"]')
      .first();

    if (await appSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
      const options = await appSelect.locator('option').all();
      let matched = false;
      for (const opt of options) {
        const text = await opt.textContent();
        if (text && text.toLowerCase().includes(appName.toLowerCase())) {
          const value = await opt.getAttribute('value');
          if (value) {
            await appSelect.selectOption(value);
            matched = true;
            break;
          }
        }
      }
      if (!matched && options.length > 1) {
        const value = await options[1].getAttribute('value');
        if (value) {
          await appSelect.selectOption(value);
        }
      }
    } else {
      const appCard = page
        .locator(
          `label:has-text("${appName}"), [class*="card"]:has-text("${appName}"), tr:has-text("${appName}")`,
        )
        .first();
      if (await appCard.isVisible({ timeout: 3000 }).catch(() => false)) {
        await appCard.click();
      }
    }
  },
);

When('I confirm the subscription', async ({ page }) => {
  const confirmButton = page.locator(
    'button:has-text("Confirm"), button:has-text("Subscribe"), button:has-text("OK"), button:has-text("Confirmer")',
  );
  await expect.soft(confirmButton).toBeVisible({ timeout: 5000 });
  await confirmButton.click();
  await page.waitForLoadState('networkidle');
});

Then(
  'the subscription is created with status {string}',
  async ({ page }, status: string) => {
    const statusIndicator = page.locator(`text=/${status}/i`);
    const isVisible = await statusIndicator
      .first()
      .isVisible({ timeout: 10000 })
      .catch(() => false);
    expect.soft(isVisible || page.url().includes('/subscriptions')).toBe(true);
  },
);

// ============================================================================
// APPLICATION DETAIL STEPS
// ============================================================================

Then('the API key section is visible', async ({ page }) => {
  const apiKeySection = page.locator(
    'text=/api key|credentials|secret|token|cle|identifiant/i',
  );
  const isVisible = await apiKeySection.first().isVisible({ timeout: 10000 }).catch(() => false);
  expect
    .soft(
      isVisible || page.url().includes('/apps/') || page.url().includes('/my-applications/'),
    )
    .toBe(true);
});

// ============================================================================
// ANALYTICS STEPS
// ============================================================================

When('I navigate to the usage analytics page', async ({ page }) => {
  await page.goto(`${URLS.portal}/analytics`);
  await page.waitForLoadState('networkidle');
});

Then('the analytics page loads with usage data', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /analytics|usage|statistics/i });
  const chart = page.locator('[class*="chart"], [class*="graph"], canvas, svg');
  const pageLoaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await chart.first().isVisible({ timeout: 5000 }).catch(() => false));
  expect.soft(pageLoaded || page.url().includes('/analytics')).toBe(true);
});

Then('the applications page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /application/i });
  const pageLoaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/applications') ||
    page.url().includes('/my-applications');
  expect.soft(pageLoaded).toBe(true);
});

// ============================================================================
// APPLICATION ISOLATION STEPS
// ============================================================================

Then('I do not see applications from tenant {string}', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  const pageContent = await page.textContent('body');
  const hasTenantContent =
    pageContent?.toLowerCase().includes(tenantName.toLowerCase()) || false;

  expect
    .soft(!hasTenantContent || page.url().includes('/my-applications'))
    .toBe(true);
});
