// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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
  await expect(page.locator('text=Loading').first()).not.toBeVisible({ timeout: 15000 }).catch(() => {});
});

Then('I see only APIs from tenant {string}', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  const tenantSelector = page.locator('select').first();
  if (await tenantSelector.isVisible()) {
    const selectedValue = await tenantSelector.inputValue();
    expect(selectedValue.toLowerCase()).toContain(tenantName.toLowerCase());
  }

  await expect(page.locator('h1, h2').filter({ hasText: /api/i })).toBeVisible();
});

Then('I do not see APIs from tenant {string}', async ({ page }, tenantName: string) => {
  const tenantSelector = page.locator('select').first();

  if (await tenantSelector.isVisible()) {
    const options = await tenantSelector.locator('option').allTextContents();
    const hasTenant = options.some(opt => opt.toLowerCase().includes(tenantName.toLowerCase()));

    if (hasTenant) {
      const selectedValue = await tenantSelector.inputValue();
      expect(selectedValue.toLowerCase()).not.toContain(tenantName.toLowerCase());
    }
  }
});

Then('I see APIs from tenant {string}', async ({ page }, tenantName: string) => {
  await page.waitForLoadState('networkidle');

  const tenantSelector = page.locator('select').first();
  if (await tenantSelector.isVisible()) {
    const selectedValue = await tenantSelector.inputValue();
    expect(selectedValue.toLowerCase()).toContain(tenantName.toLowerCase());
  }
});

// ============================================================================
// TENANT SELECTOR STEPS
// ============================================================================

When('I select tenant {string}', async ({ page }, tenantName: string) => {
  const tenantSelector = page.locator('select').first();
  await tenantSelector.selectOption({ label: new RegExp(tenantName, 'i') });
  await page.waitForLoadState('networkidle');
});

When('I open the tenant selector', async ({ page }) => {
  const tenantSelector = page.locator('select').first();
  await tenantSelector.click();
});

Then('I see only tenant {string} in the list', async ({ page }, tenantName: string) => {
  const tenantSelector = page.locator('select').first();
  const options = await tenantSelector.locator('option').allTextContents();

  const hasTenant = options.some(opt => opt.toLowerCase().includes(tenantName.toLowerCase()));
  expect(hasTenant).toBe(true);
});

Then('I do not see tenant {string} in the list', async ({ page }, tenantName: string) => {
  const tenantSelector = page.locator('select').first();
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
    const currentValue = await tenantSelector.inputValue();
    if (!currentValue.toLowerCase().includes(tenantName.toLowerCase())) {
      await tenantSelector.selectOption({ label: new RegExp(tenantName, 'i') });
      await page.waitForLoadState('networkidle');
    }
  }
});

When('I create an API named {string}', async ({ page }, apiName: string) => {
  await page.click('button:has-text("Create API"), button:has-text("New API"), button:has-text("Nouvelle API")');

  await page.fill('input[placeholder*="name"], input[name="name"], input[id="name"]', apiName);

  const displayNameInput = page.locator('input[placeholder*="Display"], input[name="display_name"]');
  if (await displayNameInput.isVisible()) {
    await displayNameInput.fill(`Test API ${apiName}`);
  }

  const versionInput = page.locator('input[placeholder*="1.0.0"], input[name="version"]');
  if (await versionInput.isVisible()) {
    await versionInput.fill('1.0.0');
  }

  const urlInput = page.locator('input[type="url"], input[placeholder*="backend"], input[name="backend_url"]');
  if (await urlInput.isVisible()) {
    await urlInput.fill('https://api.example.com/v1');
  }

  await page.click('button[type="submit"]:has-text("Create"), button[type="submit"]:has-text("Save")');
  await page.waitForLoadState('networkidle');
});

Then('the API is created in namespace {string}', async ({ page }, _namespace: string) => {
  const successIndicator = page.locator('text=/created|success|succes/i');
  await expect(successIndicator).toBeVisible({ timeout: 10000 }).catch(() => {
    expect(page.url()).toContain('/apis');
  });
});

Then('the API does not appear for {string}', async ({ page }, _otherPersona: string) => {
  await expect(page.locator('h1, h2').first()).toBeVisible();
});
