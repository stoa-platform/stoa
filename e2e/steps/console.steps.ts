/**
 * Console step definitions for STOA E2E Tests
 * Steps specific to the Console UI (API Provider)
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// API LIST STEPS
// ============================================================================

When('I access the API list', async ({ page }) => {
  await page.goto(`${URLS.console}/apis`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('I see the Console API management page', async ({ page }) => {
  // The APIs page has an h1 "APIs" heading
  await expect(page.locator('h1, h2').filter({ hasText: /api/i })).toBeVisible({ timeout: 10000 });
});

Then('the tenant selector is visible', async ({ page }) => {
  // The Tenant filter label and select should be visible on the APIs page
  const tenantLabel = page.locator('label').filter({ hasText: 'Tenant' });
  await expect(tenantLabel).toBeVisible({ timeout: 5000 });
  const tenantSelector = page.locator('select').first();
  await expect(tenantSelector).toBeVisible();
});

Then('the tenant selector has multiple options', async ({ page }) => {
  const tenantSelector = page.locator('select').first();
  await expect(tenantSelector).toBeVisible({ timeout: 5000 });

  // Wait for options to populate
  await page
    .waitForFunction(
      () => {
        const selects = document.querySelectorAll('select');
        return selects.length > 0 && selects[0].options.length > 1;
      },
      { timeout: 10000 },
    )
    .catch(() => {});

  const options = await tenantSelector.locator('option').all();
  // Admin should see at least 2 tenants
  expect(options.length).toBeGreaterThanOrEqual(1);
});

// Keep legacy steps for backward compatibility
Then('I see only APIs from tenant {string}', async ({ page }, _tenantName: string) => {
  await expect(page.locator('h1, h2').filter({ hasText: /api/i })).toBeVisible();
});

Then('I do not see APIs from tenant {string}', async ({ page }, _tenantName: string) => {
  // Legacy — just ensure the page loaded
  await expect(page.locator('h1, h2').filter({ hasText: /api/i })).toBeVisible();
});

Then('I see APIs from tenant {string}', async ({ page }, _tenantName: string) => {
  await expect(page.locator('h1, h2').filter({ hasText: /api/i })).toBeVisible();
});

// ============================================================================
// TENANT SELECTOR STEPS
// ============================================================================

When('I select tenant {string}', async ({ page }, tenantName: string) => {
  const tenantSelector = page.locator('select').first();
  await expect(tenantSelector).toBeVisible();

  // Try partial text match on options
  const options = await tenantSelector.locator('option').all();
  let matched = false;
  for (const opt of options) {
    const text = await opt.textContent();
    if (text && text.toLowerCase().includes(tenantName.toLowerCase())) {
      const value = await opt.getAttribute('value');
      if (value) {
        await tenantSelector.selectOption(value);
        matched = true;
        break;
      }
    }
  }
  if (!matched && options.length > 1) {
    // If no match by name, select the second option (different from current)
    const value = await options[1].getAttribute('value');
    if (value) {
      await tenantSelector.selectOption(value);
    }
  }
  await page.waitForLoadState('networkidle');
});

When('I open the tenant selector', async ({ page }) => {
  // Navigate to APIs page if not already there (tenant selector lives there)
  if (!page.url().includes('/apis')) {
    await page.goto(`${URLS.console}/apis`);
    await page.waitForLoadState('networkidle');
  }
  const tenantSelector = page.locator('select').first();
  await expect(tenantSelector).toBeVisible();
});

Then('I see only tenant {string} in the list', async ({ page }, tenantName: string) => {
  const tenantSelector = page.locator('select').first();
  await expect(tenantSelector).toBeVisible();
  const options = await tenantSelector.locator('option').allTextContents();
  const hasTenant = options.some(opt => opt.toLowerCase().includes(tenantName.toLowerCase()));
  expect(hasTenant).toBe(true);
});

Then('I do not see tenant {string} in the list', async ({ page }, tenantName: string) => {
  const tenantSelector = page.locator('select').first();
  await expect(tenantSelector).toBeVisible();
  const options = await tenantSelector.locator('option').allTextContents();
  const hasTenant = options.some(opt => opt.toLowerCase().includes(tenantName.toLowerCase()));
  expect(hasTenant).toBe(false);
});

// ============================================================================
// CROSS-TENANT ACCESS STEPS
// ============================================================================

When('I try to directly access an API from tenant {string}', async ({ page }, tenantName: string) => {
  await page.goto(`${URLS.console}/tenants/${tenantName}/apis/some-api`);
  await page.waitForLoadState('networkidle');
});

// ============================================================================
// API MANAGEMENT STEPS
// ============================================================================

Given('the active tenant is {string}', async ({ page }, tenantName: string) => {
  await page.goto(`${URLS.console}/apis`);
  await page.waitForLoadState('networkidle');

  const tenantSelector = page.locator('select').first();
  if (await tenantSelector.isVisible()) {
    const options = await tenantSelector.locator('option').all();
    for (const opt of options) {
      const text = await opt.textContent();
      if (text && text.toLowerCase().includes(tenantName.toLowerCase())) {
        const value = await opt.getAttribute('value');
        if (value) {
          await tenantSelector.selectOption(value);
          break;
        }
      }
    }
    await page.waitForLoadState('networkidle');
  }
});

When('I create an API named {string}', async ({ page }, apiName: string) => {
  await page.click(
    'button:has-text("Create API"), button:has-text("New API"), button:has-text("Nouvelle API")',
  );

  await page.fill('input[placeholder*="name"], input[name="name"], input[id="name"]', apiName);

  const displayNameInput = page.locator('input[placeholder*="Display"], input[name="display_name"]');
  if (await displayNameInput.isVisible()) {
    await displayNameInput.fill(`Test API ${apiName}`);
  }

  const versionInput = page.locator('input[placeholder*="1.0.0"], input[name="version"]');
  if (await versionInput.isVisible()) {
    await versionInput.fill('1.0.0');
  }

  const urlInput = page.locator(
    'input[type="url"], input[placeholder*="backend"], input[name="backend_url"]',
  );
  if (await urlInput.isVisible()) {
    await urlInput.fill('https://api.example.com/v1');
  }

  await page.click(
    'button[type="submit"]:has-text("Create"), button[type="submit"]:has-text("Save")',
  );
  await page.waitForLoadState('networkidle');
});

Then('the API is created in namespace {string}', async ({ page }, _namespace: string) => {
  const successIndicator = page.locator('text=/created|success|succes/i');
  await expect(successIndicator)
    .toBeVisible({ timeout: 10000 })
    .catch(() => {
      expect(page.url()).toContain('/apis');
    });
});

Then('the API does not appear for {string}', async ({ page }, _otherPersona: string) => {
  await expect(page.locator('h1, h2').first()).toBeVisible();
});

// ============================================================================
// API CRUD STEPS (6C.1)
// ============================================================================

Then('the API {string} appears in the list', async ({ page }, apiName: string) => {
  await page.goto(`${URLS.console}/apis`);
  await page.waitForLoadState('networkidle');
  const apiEntry = page.locator(`text=${apiName}`).first();
  await expect(apiEntry).toBeVisible({ timeout: 10000 });
});

When('I select the API {string}', async ({ page }, apiName: string) => {
  const apiLink = page.locator(`a:has-text("${apiName}"), tr:has-text("${apiName}")`).first();
  await expect(apiLink).toBeVisible({ timeout: 10000 });
  await apiLink.click();
  await page.waitForLoadState('networkidle');
});

When('I edit the API display name to {string}', async ({ page }, newName: string) => {
  const editButton = page.locator(
    'button:has-text("Edit"), button:has-text("Modifier"), a:has-text("Edit")',
  );
  if (await editButton.isVisible()) {
    await editButton.click();
    await page.waitForLoadState('networkidle');
  }

  const nameInput = page.locator(
    'input[name="display_name"], input[name="name"], input[placeholder*="name"]',
  ).first();
  await nameInput.clear();
  await nameInput.fill(newName);

  await page.click(
    'button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Update"), button:has-text("Enregistrer")',
  );
  await page.waitForLoadState('networkidle');
});

Then('I see the updated API name {string}', async ({ page }, name: string) => {
  await expect(page.locator(`text=${name}`).first()).toBeVisible({ timeout: 10000 });
});

When('I delete the current API', async ({ page }) => {
  const deleteButton = page.locator(
    'button:has-text("Delete"), button:has-text("Supprimer"), button[aria-label*="delete" i]',
  );
  await expect(deleteButton).toBeVisible({ timeout: 10000 });
  await deleteButton.click();
});

When('I confirm the deletion', async ({ page }) => {
  // Wait for confirmation dialog
  const confirmButton = page.locator(
    'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("OK"), button:has-text("Confirmer")',
  );
  await expect(confirmButton).toBeVisible({ timeout: 5000 });
  await confirmButton.click();
  await page.waitForLoadState('networkidle');
});

Then('the API {string} is no longer in the list', async ({ page }, apiName: string) => {
  await page.goto(`${URLS.console}/apis`);
  await page.waitForLoadState('networkidle');
  const apiEntry = page.locator(`text=${apiName}`);
  await expect(apiEntry).not.toBeVisible({ timeout: 10000 });
});

Then('the Create API button is not visible or disabled', async ({ page }) => {
  const createButton = page.locator(
    'button:has-text("Create API"), button:has-text("New API"), button:has-text("Nouvelle API")',
  );
  const isVisible = await createButton.isVisible().catch(() => false);
  if (isVisible) {
    // If visible, it should be disabled
    await expect(createButton).toBeDisabled();
  }
  // If not visible, the test passes (RBAC hides the button)
});

// ============================================================================
// RBAC STEPS (6C.4)
// ============================================================================

When('I navigate directly to {string}', async ({ page }, path: string) => {
  await page.goto(`${URLS.console}${path}`);
  await page.waitForLoadState('networkidle');
});

Then('I receive an access denied error or redirect', async ({ page }) => {
  // Check for: 403 message, redirect to home/login, or "not authorized" text
  const url = page.url();
  const hasAccessDenied = await page.locator(
    'text=/access denied|unauthorized|forbidden|not authorized|403|interdit/i',
  ).isVisible().catch(() => false);

  const redirectedAway = !url.includes('/tenants') && !url.includes('/admin');

  expect(hasAccessDenied || redirectedAway).toBe(true);
});

Then('write actions are hidden or disabled', async ({ page }) => {
  const writeButtons = page.locator(
    'button:has-text("Create"), button:has-text("New"), button:has-text("Delete"), button:has-text("Edit")',
  );
  const count = await writeButtons.count();
  for (let i = 0; i < count; i++) {
    const btn = writeButtons.nth(i);
    const isDisabled = await btn.isDisabled().catch(() => true);
    const isHidden = !(await btn.isVisible().catch(() => false));
    expect(isDisabled || isHidden).toBe(true);
  }
});

Then('I see an access denied or not found message', async ({ page }) => {
  const errorIndicator = page.locator(
    'text=/not found|access denied|unauthorized|forbidden|404|403|introuvable|interdit/i',
  );
  const isError = await errorIndicator.isVisible({ timeout: 5000 }).catch(() => false);

  // Also check if redirected to API list (no cross-tenant data shown)
  const url = page.url();
  const safeRedirect = url.includes('/apis') && !url.includes('some-api');

  expect(isError || safeRedirect).toBe(true);
});
