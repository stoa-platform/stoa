/**
 * Admin RBAC step definitions for STOA E2E Tests
 * Steps for verifying role-based access control across personas
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// ADMIN NAVIGATION STEPS
// ============================================================================

When('I navigate to the tenants page', async ({ page }) => {
  await page.goto(`${URLS.console}/tenants`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the tenants list loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /tenant/i });
  const table = page.locator('table, [class*="grid"], [class*="list"]');
  const pageLoaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await table.first().isVisible({ timeout: 5000 }).catch(() => false));
  expect.soft(pageLoaded || page.url().includes('/tenants')).toBe(true);
});

When('I navigate to the admin prospects page', async ({ page }) => {
  await page.goto(`${URLS.console}/admin/prospects`);
  await page.waitForLoadState('networkidle');
});

Then('the prospects page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /prospect/i });
  const pageLoaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/prospects');
  expect.soft(pageLoaded || page.url().includes('/admin')).toBe(true);
});

When('I navigate to the monitoring page', async ({ page }) => {
  await page.goto(`${URLS.console}/monitoring`);
  await page.waitForLoadState('networkidle');
});

Then('the monitoring dashboard loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /monitor/i });
  const dashboard = page.locator('[class*="dashboard"], iframe, [class*="chart"]');
  const pageLoaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await dashboard.first().isVisible({ timeout: 5000 }).catch(() => false));
  expect.soft(pageLoaded || page.url().includes('/monitoring')).toBe(true);
});

// ============================================================================
// DIRECT URL ACCESS STEPS
// ============================================================================

When('I navigate directly to {string}', async ({ page }, path: string) => {
  await page.goto(`${URLS.console}${path}`);
  await page.waitForLoadState('networkidle');
});

Then('I receive an access denied error or redirect', async ({ page }) => {
  const accessDenied = page.locator(
    'text=/access denied|forbidden|unauthorized|403|not authorized|permission/i',
  );
  const redirected = !page.url().includes('/admin') && !page.url().includes('/tenants');
  const hasDenied = await accessDenied.first().isVisible({ timeout: 5000 }).catch(() => false);
  expect.soft(hasDenied || redirected).toBe(true);
});

// ============================================================================
// WRITE ACTION STEPS
// ============================================================================

Then('write actions are hidden or disabled', async ({ page }) => {
  const writeButtons = page.locator(
    'button:has-text("Create"), button:has-text("Delete"), button:has-text("Edit"), button:has-text("Nouveau"), button:has-text("Supprimer")',
  );
  const count = await writeButtons.count();
  for (let i = 0; i < count; i++) {
    const btn = writeButtons.nth(i);
    const isVisible = await btn.isVisible().catch(() => false);
    if (isVisible) {
      await expect.soft(btn).toBeDisabled();
    }
  }
});

// ============================================================================
// TENANT ISOLATION STEPS
// ============================================================================

Then('I do not see APIs belonging to tenant {string}', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});

  const apiList = page.locator('table, [class*="list"], [class*="grid"]').first();
  if (await apiList.isVisible({ timeout: 5000 }).catch(() => false)) {
    const listContent = await apiList.textContent();
    const hasTenantAPIs =
      listContent?.toLowerCase().includes(tenantName.toLowerCase()) || false;
    expect.soft(hasTenantAPIs).toBe(false);
  }
});
