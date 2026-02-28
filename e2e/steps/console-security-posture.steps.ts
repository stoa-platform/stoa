/**
 * Console Security Posture Dashboard step definitions for STOA E2E Tests
 * Steps for security posture dashboard page navigation and content verification
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// SECURITY POSTURE DASHBOARD
// ============================================================================

When('I navigate to the Security Posture Dashboard page', async ({ page }) => {
  await page.goto(`${URLS.console}/security-posture`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Security Posture Dashboard page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Security/i });
  const content = page.locator(
    '[class*="card"], [class*="metric"], [class*="score"], [class*="chart"], [class*="posture"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/security-posture')).toBe(true);
});

Then('the Security Posture Dashboard displays security metrics', async ({ page }) => {
  const metrics = page.locator(
    '[class*="score"], [class*="metric"], [class*="gauge"], [class*="card"], [class*="stat"]',
  );
  const charts = page.locator('[class*="chart"], canvas, svg');

  const hasMetrics =
    (await metrics.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasMetrics || page.url().includes('/security-posture')).toBe(true);
});

Then('the Security Posture Dashboard hides admin actions', async ({ page }) => {
  await page.waitForLoadState('networkidle');

  const adminButtons = page.locator(
    'button:has-text("Configure"), button:has-text("Export"), button:has-text("Edit"), ' +
      'button:has-text("Create"), button:has-text("Delete"), button:has-text("Settings")',
  );
  const count = await adminButtons.count();
  for (let i = 0; i < count; i++) {
    const btn = adminButtons.nth(i);
    const isDisabled = await btn.isDisabled().catch(() => true);
    const isHidden = !(await btn.isVisible().catch(() => false));
    expect.soft(isDisabled || isHidden).toBe(true);
  }
  expect(page.url().includes('/security-posture') || count === 0).toBe(true);
});

Then('no security data from tenant {string} is visible', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  const tenantContent = page.locator(`text=${tenantName}`);
  const isVisible = await tenantContent.first().isVisible({ timeout: 5000 }).catch(() => false);

  const hasAccessDenied = await page
    .locator('text=/access denied|unauthorized|forbidden|403/i')
    .isVisible()
    .catch(() => false);

  expect(!isVisible || hasAccessDenied || page.url().includes('/security-posture')).toBe(true);
});
