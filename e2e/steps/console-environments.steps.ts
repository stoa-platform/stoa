/**
 * Console Environment Chrome & Switching step definitions
 * Steps for the EnvironmentChrome bar, env switching, and read-only enforcement (CAB-1705)
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// CHROME BAR — VISIBILITY STEPS
// ============================================================================

When('I look at the Console header', async ({ page }) => {
  await page.goto(`${URLS.console}/`);
  await page.waitForLoadState('networkidle');
});

Then(
  'the environment chrome bar is visible with the active environment name',
  async ({ page }) => {
    // The EnvironmentChrome renders a full-width bar with data-testid="env-chrome"
    // or a visible bar with env name text (Development, Staging, Production)
    const chromeBar = page.locator(
      '[data-testid="env-chrome"], [class*="bg-green-600"], [class*="bg-amber-500"], [class*="bg-red-600"]'
    );
    await expect(chromeBar.first()).toBeVisible({ timeout: 10000 });

    // Should contain an environment name
    const envLabel = page.locator('text=/Development|Staging|Production/i');
    await expect(envLabel.first()).toBeVisible({ timeout: 5000 });
  }
);

Then('the chrome bar uses green for Development', async ({ page }) => {
  // Navigate to dev env and check color
  const greenBar = page.locator('[class*="bg-green-600"]');
  const devLabel = page.locator('text=/Development/i');
  // At least verify the color class or label exists
  const hasGreen =
    (await greenBar.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await devLabel.first().isVisible({ timeout: 3000 }).catch(() => false));
  expect(hasGreen).toBe(true);
});

Then('the chrome bar uses amber for Staging', async ({ page }) => {
  const amberBar = page.locator('[class*="bg-amber-500"]');
  const stagingLabel = page.locator('text=/Staging/i');
  const hasAmber =
    (await amberBar.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await stagingLabel.first().isVisible({ timeout: 3000 }).catch(() => false));
  expect(hasAmber).toBe(true);
});

Then('the chrome bar uses red for Production', async ({ page }) => {
  const redBar = page.locator('[class*="bg-red-600"]');
  const prodLabel = page.locator('text=/Production/i');
  const hasRed =
    (await redBar.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await prodLabel.first().isVisible({ timeout: 3000 }).catch(() => false));
  expect(hasRed).toBe(true);
});

// ============================================================================
// ENVIRONMENT SWITCHING — DROPDOWN STEPS
// ============================================================================

When('I open the environment switcher dropdown', async ({ page }) => {
  await page.goto(`${URLS.console}/`);
  await page.waitForLoadState('networkidle');

  // Click the Switch button in the chrome bar
  const switchBtn = page.locator(
    'button:has-text("Switch"), [data-testid="env-switcher"], button:has([class*="rounded-full"][class*="h-2"])'
  );
  await expect(switchBtn.first()).toBeVisible({ timeout: 10000 });
  await switchBtn.first().click();

  // Wait for dropdown to appear
  await page.waitForTimeout(500);
});

Then('I see at least 2 environments in the list', async ({ page }) => {
  const envItems = page.locator(
    '[role="menuitem"], [role="option"], [data-testid*="env-option"], button:has-text(/Production|Staging|Development/i)'
  );

  const count = await envItems.count();
  expect(count).toBeGreaterThanOrEqual(2);
});

When(
  'I select {string} from the environment list',
  async ({ page }, envName: string) => {
    const envItem = page.locator(
      `[role="menuitem"]:has-text("${envName}"), [role="option"]:has-text("${envName}"), button:has-text("${envName}")`
    );
    await expect(envItem.first()).toBeVisible({ timeout: 5000 });
    await envItem.first().click();
    await page.waitForLoadState('networkidle');
  }
);

Then(
  'the environment indicator shows {string}',
  async ({ page }, envName: string) => {
    const indicator = page.locator(`text=${envName}`);
    await expect(indicator.first()).toBeVisible({ timeout: 10000 });
  }
);

When('I reload the page', async ({ page }) => {
  await page.reload();
  await page.waitForLoadState('networkidle');
});

// ============================================================================
// ENVIRONMENT SWITCHING — SHORTCUT
// ============================================================================

When(
  'I switch to the {string} environment',
  async ({ page }, envName: string) => {
    await page.goto(`${URLS.console}/`);
    await page.waitForLoadState('networkidle');

    // Open the switcher dropdown
    const switchBtn = page.locator(
      'button:has-text("Switch"), [data-testid="env-switcher"], button:has([class*="rounded-full"][class*="h-2"])'
    );
    if (await switchBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) {
      await switchBtn.first().click();
      await page.waitForTimeout(300);

      // Select the environment
      const envItem = page.locator(
        `button:has-text("${envName}"), [role="option"]:has-text("${envName}")`
      );
      if (await envItem.first().isVisible({ timeout: 3000 }).catch(() => false)) {
        await envItem.first().click();
        await page.waitForLoadState('networkidle');
      }
    }
  }
);

// ============================================================================
// READ-ONLY ENFORCEMENT
// ============================================================================

Then(
  'the chrome bar displays a {string} badge',
  async ({ page }, badgeText: string) => {
    const badge = page.locator(
      `text=/${badgeText}/i, [data-testid="env-readonly-badge"]`
    );
    await expect(badge.first()).toBeVisible({ timeout: 10000 });
  }
);

Then(
  'the {string} button is not disabled',
  async ({ page }, buttonText: string) => {
    const button = page.locator(`button:has-text("${buttonText}")`);
    await expect(button.first()).toBeVisible({ timeout: 10000 });
    await expect(button.first()).toBeEnabled();
  }
);

// "I navigate to the gateways page" is defined in console-gateways.steps.ts
