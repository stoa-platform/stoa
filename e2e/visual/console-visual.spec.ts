import { test, expect } from '@playwright/test';
import { setupMockRoutes, injectMockAuth } from '../smoke-mock/mock-routes';
import { buildMaskLocators } from './mask-helper';

/**
 * Console Visual Regression — 3 key pages (CAB-1994)
 *
 * Golden baselines in e2e/golden/console-visual/.
 * Dynamic values masked via data-testid suffix convention.
 */

test.beforeEach(async ({ page }) => {
  await setupMockRoutes(page);
  await injectMockAuth(page);
});

test('Dashboard visual baseline', async ({ page }) => {
  await page.goto('/operations');
  await page.waitForLoadState('networkidle');
  const mask = buildMaskLocators(page);
  await expect(page).toHaveScreenshot('dashboard.png', { mask, fullPage: true });
});

test('Tenants visual baseline', async ({ page }) => {
  await page.goto('/tenants');
  await page.waitForLoadState('networkidle');
  const mask = buildMaskLocators(page);
  await expect(page).toHaveScreenshot('tenants.png', { mask, fullPage: true });
});

test('Gateways visual baseline', async ({ page }) => {
  await page.goto('/gateway');
  await page.waitForLoadState('networkidle');
  const mask = buildMaskLocators(page);
  await expect(page).toHaveScreenshot('gateways.png', { mask, fullPage: true });
});
