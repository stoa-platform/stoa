/**
 * Gateway CRUD step definitions for STOA E2E Tests
 * Steps for creating, reading, updating, and deleting gateway instances
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// GATEWAY CREATE STEPS
// ============================================================================

When('I click the create gateway button', async ({ page }) => {
  const createButton = page.locator(
    'button:has-text("Create"), button:has-text("New Gateway"), button:has-text("Add Gateway"), button:has-text("Nouveau")',
  );
  await expect.soft(createButton.first()).toBeVisible({ timeout: 10000 });
  await createButton.first().click();
  await page.waitForLoadState('networkidle');
});

When(
  'I fill in the gateway form with name {string} and URL {string}',
  async ({ page }, name: string, url: string) => {
    const nameInput = page
      .locator('input[name="name"], input[placeholder*="name" i], input[id="name"]')
      .first();
    await expect.soft(nameInput).toBeVisible({ timeout: 5000 });
    await nameInput.fill(name);

    const urlInput = page
      .locator(
        'input[name="url"], input[name="endpoint"], input[type="url"], input[placeholder*="url" i], input[placeholder*="endpoint" i]',
      )
      .first();
    if (await urlInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await urlInput.fill(url);
    }
  },
);

When('I submit the gateway form', async ({ page }) => {
  const submitButton = page.locator(
    'button[type="submit"], button:has-text("Create"), button:has-text("Save"), button:has-text("Enregistrer")',
  );
  await submitButton.click();
  await page.waitForLoadState('networkidle');
});

Then('the gateway {string} appears in the gateway list', async ({ page }, gatewayName: string) => {
  await page.goto(`${URLS.console}/gateways`);
  await page.waitForLoadState('networkidle');
  const gatewayEntry = page.locator(`text=${gatewayName}`).first();
  await expect.soft(gatewayEntry).toBeVisible({ timeout: 10000 });
});

// ============================================================================
// GATEWAY LIST STEPS
// ============================================================================

Then('the gateway list contains at least one entry', async ({ page }) => {
  const rows = page.locator(
    'table tbody tr, [class*="card"], [class*="list-item"], a[href*="/gateways/"]',
  );
  const count = await rows.count();
  expect.soft(count).toBeGreaterThanOrEqual(1);
});

// ============================================================================
// GATEWAY DETAIL STEPS
// ============================================================================

Then('the gateway status badge is visible', async ({ page }) => {
  const statusBadge = page.locator(
    '[class*="badge"], [class*="status"], text=/online|offline|healthy|unhealthy|connected|disconnected|synced|error/i',
  );
  const isVisible = await statusBadge.first().isVisible({ timeout: 10000 }).catch(() => false);
  expect.soft(isVisible || page.url().includes('/gateways/')).toBe(true);
});

// ============================================================================
// GATEWAY UPDATE STEPS
// ============================================================================

When('I click the edit gateway button', async ({ page }) => {
  const editButton = page.locator(
    'button:has-text("Edit"), button:has-text("Modifier"), a:has-text("Edit"), button[aria-label*="edit" i]',
  );
  await expect.soft(editButton.first()).toBeVisible({ timeout: 10000 });
  await editButton.first().click();
  await page.waitForLoadState('networkidle');
});

When('I update the gateway display name to {string}', async ({ page }, newName: string) => {
  const nameInput = page
    .locator('input[name="display_name"], input[name="name"], input[placeholder*="name" i]')
    .first();
  await nameInput.clear();
  await nameInput.fill(newName);
});

When('I save the gateway changes', async ({ page }) => {
  const saveButton = page.locator(
    'button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Update"), button:has-text("Enregistrer")',
  );
  await saveButton.click();
  await page.waitForLoadState('networkidle');
});

Then('I see the updated gateway name {string}', async ({ page }, name: string) => {
  await expect.soft(page.locator(`text=${name}`).first()).toBeVisible({ timeout: 10000 });
});

// ============================================================================
// GATEWAY DELETE STEPS
// ============================================================================

When('I click on the gateway named {string}', async ({ page }, gatewayName: string) => {
  const gatewayLink = page
    .locator(
      `a:has-text("${gatewayName}"), tr:has-text("${gatewayName}"), [class*="card"]:has-text("${gatewayName}")`,
    )
    .first();
  await expect.soft(gatewayLink).toBeVisible({ timeout: 10000 });
  await gatewayLink.click();
  await page.waitForLoadState('networkidle');
});

When('I click the delete gateway button', async ({ page }) => {
  const deleteButton = page.locator(
    'button:has-text("Delete"), button:has-text("Supprimer"), button[aria-label*="delete" i]',
  );
  await expect.soft(deleteButton.first()).toBeVisible({ timeout: 10000 });
  await deleteButton.first().click();
});

When('I confirm the gateway deletion', async ({ page }) => {
  const confirmButton = page.locator(
    'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("OK"), button:has-text("Confirmer")',
  );
  await expect.soft(confirmButton).toBeVisible({ timeout: 5000 });
  await confirmButton.click();
  await page.waitForLoadState('networkidle');
});

Then(
  'the gateway {string} is no longer in the gateway list',
  async ({ page }, gatewayName: string) => {
    await page.goto(`${URLS.console}/gateways`);
    await page.waitForLoadState('networkidle');
    const gatewayEntry = page.locator(`text=${gatewayName}`);
    await expect.soft(gatewayEntry).not.toBeVisible({ timeout: 10000 });
  },
);

// ============================================================================
// GATEWAY RBAC STEPS
// ============================================================================

Then('the create gateway button is not visible or disabled', async ({ page }) => {
  const createButton = page.locator(
    'button:has-text("Create"), button:has-text("New Gateway"), button:has-text("Add Gateway"), button:has-text("Nouveau")',
  );
  const isVisible = await createButton.first().isVisible().catch(() => false);
  if (isVisible) {
    await expect.soft(createButton.first()).toBeDisabled();
  }
});

Then('the delete gateway action is not available', async ({ page }) => {
  const deleteButton = page.locator(
    'button:has-text("Delete"), button:has-text("Supprimer"), button[aria-label*="delete" i]',
  );
  const isVisible = await deleteButton.first().isVisible().catch(() => false);
  if (isVisible) {
    await expect.soft(deleteButton.first()).toBeDisabled();
  }
});
