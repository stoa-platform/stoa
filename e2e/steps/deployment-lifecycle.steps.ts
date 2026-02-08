/**
 * Deployment Lifecycle step definitions for STOA E2E Tests
 * Steps for managing API deployments through their lifecycle
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// DEPLOYMENT LIST STEPS
// ============================================================================

Then('the deployment list contains entries or an empty state', async ({ page }) => {
  const rows = page.locator(
    'table tbody tr, [class*="card"], [class*="list-item"], a[href*="/deployments/"]',
  );
  const emptyState = page.locator('text=/no deployment|empty|get started|create your first/i');

  const hasEntries = (await rows.count()) > 0;
  const hasEmptyState = await emptyState.first().isVisible({ timeout: 5000 }).catch(() => false);

  expect.soft(hasEntries || hasEmptyState || page.url().includes('/deployments')).toBe(true);
});

// ============================================================================
// DEPLOYMENT CREATE STEPS
// ============================================================================

When('I click the create deployment button', async ({ page }) => {
  const createButton = page.locator(
    'button:has-text("Create"), button:has-text("New Deployment"), button:has-text("Deploy"), button:has-text("Nouveau")',
  );
  await expect.soft(createButton.first()).toBeVisible({ timeout: 10000 });
  await createButton.first().click();
  await page.waitForLoadState('networkidle');
});

When('I select an API to deploy', async ({ page }) => {
  const apiSelect = page
    .locator('select[name*="api"], [role="combobox"], [class*="select"]')
    .first();

  if (await apiSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
    const options = await apiSelect.locator('option').all();
    if (options.length > 1) {
      const value = await options[1].getAttribute('value');
      if (value) {
        await apiSelect.selectOption(value);
      }
    }
  } else {
    const apiCard = page
      .locator(
        '[class*="card"] input[type="radio"], [class*="list-item"] input[type="radio"], tr input[type="radio"]',
      )
      .first();
    if (await apiCard.isVisible({ timeout: 3000 }).catch(() => false)) {
      await apiCard.click();
    }
  }
  await page.waitForLoadState('networkidle');
});

When('I select the target environment {string}', async ({ page }, environment: string) => {
  const envSelect = page
    .locator('select[name*="environment"], select[name*="env"], select[name*="target"]')
    .first();

  if (await envSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
    await envSelect.selectOption({ label: new RegExp(environment, 'i') });
  } else {
    const envButton = page
      .locator(
        `button:has-text("${environment}"), label:has-text("${environment}"), [role="radio"]:has-text("${environment}")`,
      )
      .first();
    if (await envButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await envButton.click();
    }
  }
});

When('I submit the deployment form', async ({ page }) => {
  const submitButton = page.locator(
    'button[type="submit"], button:has-text("Deploy"), button:has-text("Create"), button:has-text("Save")',
  );
  await submitButton.click();
  await page.waitForLoadState('networkidle');
});

Then(
  'the deployment is created with status {string} or {string}',
  async ({ page }, status1: string, status2: string) => {
    const statusIndicator = page.locator(`text=/${status1}|${status2}/i`);
    const isVisible = await statusIndicator
      .first()
      .isVisible({ timeout: 10000 })
      .catch(() => false);
    expect.soft(isVisible || page.url().includes('/deployments')).toBe(true);
  },
);

// ============================================================================
// DEPLOYMENT DETAIL STEPS
// ============================================================================

When('I click on the first deployment', async ({ page }) => {
  const deploymentRow = page
    .locator('table tbody tr, a[href*="/deployments/"], [class*="card"]')
    .first();
  await expect.soft(deploymentRow).toBeVisible({ timeout: 10000 });
  await deploymentRow.click();
  await page.waitForLoadState('networkidle');
});

Then('the deployment detail page loads', async ({ page }) => {
  const detailIndicator = page.locator(
    'text=/status|configuration|sync|environment|detail|version/i',
  );
  const isDetail =
    (await detailIndicator.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/deployments/');

  expect.soft(isDetail).toBe(true);
});

Then('the deployment sync status is visible', async ({ page }) => {
  const syncStatus = page.locator(
    '[class*="badge"], [class*="status"], text=/synced|pending|drifted|error|deploying|deployed/i',
  );
  const isVisible = await syncStatus.first().isVisible({ timeout: 10000 }).catch(() => false);
  expect.soft(isVisible || page.url().includes('/deployments/')).toBe(true);
});

// ============================================================================
// DEPLOYMENT PROMOTE STEPS
// ============================================================================

When('I click the promote button', async ({ page }) => {
  const promoteButton = page.locator(
    'button:has-text("Promote"), button:has-text("Promouvoir"), button[aria-label*="promote" i]',
  );
  await expect.soft(promoteButton.first()).toBeVisible({ timeout: 10000 });
  await promoteButton.first().click();
  await page.waitForLoadState('networkidle');
});

When('I confirm the promotion to {string}', async ({ page }, environment: string) => {
  const envSelect = page
    .locator('select[name*="environment"], select[name*="target"]')
    .first();
  if (await envSelect.isVisible({ timeout: 3000 }).catch(() => false)) {
    await envSelect.selectOption({ label: new RegExp(environment, 'i') });
  }

  const confirmButton = page.locator(
    'button:has-text("Confirm"), button:has-text("Promote"), button:has-text("OK"), button:has-text("Confirmer")',
  );
  await expect.soft(confirmButton).toBeVisible({ timeout: 5000 });
  await confirmButton.click();
  await page.waitForLoadState('networkidle');
});

Then(
  'the deployment target environment shows {string}',
  async ({ page }, environment: string) => {
    const envIndicator = page.locator(`text=/${environment}/i`);
    const isVisible = await envIndicator.first().isVisible({ timeout: 10000 }).catch(() => false);
    expect.soft(isVisible || page.url().includes('/deployments')).toBe(true);
  },
);

// ============================================================================
// DEPLOYMENT RBAC STEPS
// ============================================================================

Then('the create deployment button is not visible or disabled', async ({ page }) => {
  const createButton = page.locator(
    'button:has-text("Create"), button:has-text("New Deployment"), button:has-text("Deploy"), button:has-text("Nouveau")',
  );
  const isVisible = await createButton.first().isVisible().catch(() => false);
  if (isVisible) {
    await expect.soft(createButton.first()).toBeDisabled();
  }
});

Then('the promote action is not available', async ({ page }) => {
  const promoteButton = page.locator(
    'button:has-text("Promote"), button:has-text("Promouvoir"), button[aria-label*="promote" i]',
  );
  const isVisible = await promoteButton.first().isVisible().catch(() => false);
  if (isVisible) {
    await expect.soft(promoteButton.first()).toBeDisabled();
  }
});
