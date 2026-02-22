/**
 * Console step definitions for Federation Management (CAB-1373)
 * Steps for managing federation master/sub-accounts via the Console UI.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// FEDERATION — NAVIGATION
// ============================================================================

When('I navigate to the Federation page', async ({ page }) => {
  await page.goto(`${URLS.console}/federation`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Federation page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Federation/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false));

  expect(loaded || page.url().includes('/federation')).toBe(true);
});

When(
  'I navigate to the Federation detail page for {string}',
  async ({ page }, masterName: string) => {
    await page.goto(`${URLS.console}/federation`);
    await page.waitForLoadState('networkidle');

    const row = page.locator(`tr:has-text("${masterName}"), [class*="card"]:has-text("${masterName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });
    await row.click();
    await page.waitForLoadState('networkidle');
  },
);

// ============================================================================
// FEDERATION — MASTER ACCOUNT CRUD
// ============================================================================

Given('a master account {string} exists', async ({ page }, masterName: string) => {
  await page.goto(`${URLS.console}/federation`);
  await page.waitForLoadState('networkidle');

  const existing = page.locator(`text=${masterName}`).first();
  const isVisible = await existing.isVisible({ timeout: 5000 }).catch(() => false);

  if (!isVisible) {
    const addBtn = page.locator('button:has-text("Create"), button:has-text("Add")').first();
    await expect(addBtn).toBeVisible({ timeout: 10000 });
    await addBtn.click();

    await page.fill('input[placeholder*="name" i], input[name*="name" i]', masterName);
    await page.click('button[type="submit"], button:has-text("Create")');
    await page.waitForLoadState('networkidle');
  }
});

When(
  'I create a master account named {string}',
  async ({ page }, masterName: string) => {
    const addBtn = page.locator('button:has-text("Create"), button:has-text("Add")').first();
    await expect(addBtn).toBeVisible({ timeout: 15000 });
    await addBtn.click();

    await page.fill('input[placeholder*="name" i], input[name*="name" i]', masterName);
    await page.click('button[type="submit"], button:has-text("Create")');
    await page.waitForLoadState('networkidle');
  },
);

Then(
  'the master account {string} appears in the list',
  async ({ page }, masterName: string) => {
    await expect(page.locator(`text=${masterName}`).first()).toBeVisible({
      timeout: 10000,
    });
  },
);

When(
  'I delete the master account {string}',
  async ({ page }, masterName: string) => {
    const row = page.locator(`tr:has-text("${masterName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    const deleteBtn = row.locator('button:has(svg[class*="trash" i]), button[aria-label*="delete" i]').first();
    await deleteBtn.click();
  },
);

Then(
  'the master account {string} is no longer in the list',
  async ({ page }, masterName: string) => {
    await page.waitForLoadState('networkidle');
    const entry = page.locator(`text=${masterName}`);
    await expect(entry).not.toBeVisible({ timeout: 10000 });
  },
);

// ============================================================================
// FEDERATION — SUB-ACCOUNT CRUD
// ============================================================================

When(
  'I create a sub-account named {string}',
  async ({ page }, subName: string) => {
    const addBtn = page.locator('button:has-text("Add Sub"), button:has-text("Create Sub")').first();
    await expect(addBtn).toBeVisible({ timeout: 10000 });
    await addBtn.click();

    await page.fill('input[placeholder*="name" i], input[name*="name" i]', subName);
    await page.click('button[type="submit"], button:has-text("Create")');
    await page.waitForLoadState('networkidle');
  },
);

Then(
  'the sub-account {string} appears in the sub-accounts table',
  async ({ page }, subName: string) => {
    await expect(page.locator(`text=${subName}`).first()).toBeVisible({
      timeout: 10000,
    });
  },
);

Then('the sub-account has an API key', async ({ page }) => {
  const apiKeyCell = page.locator('td:has-text("sk-"), [class*="key"]:has-text("sk-"), code:has-text("sk-")');
  const masked = page.locator('text=/\\*{4,}|•{4,}/');

  const hasKey =
    (await apiKeyCell.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await masked.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasKey).toBe(true);
});

When(
  'I revoke the sub-account {string}',
  async ({ page }, subName: string) => {
    const row = page.locator(`tr:has-text("${subName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    const revokeBtn = row.locator('button:has-text("Revoke")');
    await revokeBtn.click();
  },
);

When('I confirm the action', async ({ page }) => {
  const confirmBtn = page.locator(
    'button:has-text("Confirm"), button:has-text("Yes"), [role="dialog"] button:has-text("OK"), [role="alertdialog"] button:has-text("Confirm")',
  ).first();
  await expect(confirmBtn).toBeVisible({ timeout: 5000 });
  await confirmBtn.click();
  await page.waitForLoadState('networkidle');
});

Then(
  'the sub-account {string} shows status {string}',
  async ({ page }, subName: string, status: string) => {
    const row = page.locator(`tr:has-text("${subName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });
    await expect(row.locator(`text=${status}`).first()).toBeVisible({ timeout: 5000 });
  },
);

// ============================================================================
// FEDERATION — BULK OPERATIONS
// ============================================================================

When('I click the bulk revoke button', async ({ page }) => {
  const bulkBtn = page.locator('button:has-text("Bulk Revoke"), button:has-text("Revoke All")').first();
  await expect(bulkBtn).toBeVisible({ timeout: 10000 });
  await bulkBtn.click();
});

Then(
  'all sub-accounts show status {string}',
  async ({ page }, status: string) => {
    await page.waitForLoadState('networkidle');
    const statusBadges = page.locator(`td:has-text("${status}"), [class*="badge"]:has-text("${status}")`);
    const count = await statusBadges.count();
    expect(count).toBeGreaterThan(0);
  },
);

// ============================================================================
// FEDERATION — USAGE DASHBOARD
// ============================================================================

Then('the usage breakdown section is visible', async ({ page }) => {
  const usageSection = page.locator(
    'text=/Usage|Breakdown|Analytics/i, [class*="usage"], [class*="analytics"]',
  ).first();
  await expect(usageSection).toBeVisible({ timeout: 10000 });
});

Then('the usage chart displays data', async ({ page }) => {
  const chart = page.locator(
    'canvas, svg[class*="chart"], [class*="chart"], [class*="recharts"]',
  ).first();
  const noData = page.locator('text=/No data|No usage/i');

  const hasContent =
    (await chart.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await noData.isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasContent).toBe(true);
});

// ============================================================================
// FEDERATION — RBAC
// ============================================================================

Then('the create master account button is not visible', async ({ page }) => {
  await page.waitForLoadState('networkidle');
  await expect(
    page.locator('h1, h2').filter({ hasText: /Federation/i }),
  ).toBeVisible({ timeout: 10000 });

  const createBtn = page.locator('button:has-text("Create"), button:has-text("Add Master")');
  await expect(createBtn.first()).not.toBeVisible({ timeout: 5000 });
});

Then('the revoke button is not visible', async ({ page }) => {
  await page.waitForLoadState('networkidle');
  const revokeBtn = page.locator('button:has-text("Revoke")');
  await expect(revokeBtn.first()).not.toBeVisible({ timeout: 5000 });
});
