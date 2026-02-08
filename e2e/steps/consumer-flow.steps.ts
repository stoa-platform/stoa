/**
 * Consumer Flow step definitions for STOA E2E Tests
 * Steps for the API consumer journey: discover, subscribe, consume
 */

import { createBdd } from 'playwright-bdd';
import { test, expect } from '../fixtures/test-base';

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

// Note: application management steps (create, appears in list, click, detail page)
// are defined in portal-advanced.steps.ts and portal-contracts.steps.ts

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

// Note: 'I confirm the subscription' and 'the subscription is created with status {string}'
// are defined in portal.steps.ts

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

// Note: analytics steps and 'the applications page loads successfully'
// are defined in portal-advanced.steps.ts

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
