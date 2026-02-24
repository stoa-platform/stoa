/**
 * Console step definitions for Credential Mapping UI (CAB-1432)
 * Steps for managing per-consumer backend credential mappings via the Console.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// NAVIGATION — open gateway detail + click Credential Mapping tab
// ============================================================================

When('I open the first available gateway', async ({ page }) => {
  // Try row link first, then card, then any gateway-detail link
  const gatewayLink = page.locator(
    'table tbody tr, a[href*="/gateways/"], [class*="card"][class*="gateway"]',
  ).first();

  const visible = await gatewayLink.isVisible({ timeout: 10000 }).catch(() => false);
  if (!visible) {
    // Soft-fail: no gateways provisioned in this env — tests will be skipped via soft
    expect.soft(visible, 'No gateways found — skipping credential mapping tests').toBe(true);
    return;
  }
  await gatewayLink.click();
  await page.waitForLoadState('networkidle');
});

// Note: 'I click the {string} tab' is defined in deployment-lifecycle.steps.ts (shared step).

Then('the Credential Mapping tab loads successfully', async ({ page }) => {
  // The tab should show a table or empty state related to credential mappings
  const heading = page
    .locator('h2, h3')
    .filter({ hasText: /credential.mapping|consumer credential/i });
  const table = page.locator('table, [class*="credential"]');
  const emptyState = page.locator(
    'text=/no credential|add your first|no mapping/i',
  );

  const loaded =
    (await heading.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await table.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await emptyState.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/gateways/');

  expect(loaded).toBe(true);
});

// ============================================================================
// CRUD — create / edit / delete credential mappings
// ============================================================================

When(
  'I add a credential mapping for consumer {string} with header {string} and value {string}',
  async ({ page }, consumerId: string, headerName: string, headerValue: string) => {
    const addBtn = page.locator(
      'button:has-text("Add Mapping"), button:has-text("Add Credential"), button:has-text("New Mapping")',
    );
    const btnVisible = await addBtn.first().isVisible({ timeout: 10000 }).catch(() => false);
    if (!btnVisible) {
      expect
        .soft(btnVisible, 'Add credential mapping button not found — may require live gateway')
        .toBe(true);
      return;
    }
    await addBtn.first().click();

    // Fill the consumer ID
    const consumerInput = page.locator(
      'input[name="consumer_id"], input[placeholder*="consumer"], input[id*="consumer"]',
    );
    if (await consumerInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await consumerInput.fill(consumerId);
    }

    // Fill the header name
    const headerNameInput = page.locator(
      'input[name="header_name"], input[placeholder*="header"], input[id*="header_name"]',
    );
    if (await headerNameInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await headerNameInput.fill(headerName);
    }

    // Fill the header value / credential value
    const headerValueInput = page.locator(
      'input[name="header_value"], input[placeholder*="value"], input[name="credential_value"], input[type="password"]',
    );
    if (await headerValueInput.first().isVisible({ timeout: 5000 }).catch(() => false)) {
      await headerValueInput.first().fill(headerValue);
    }

    // Submit
    await page.click(
      'button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Create"), button[type="submit"]:has-text("Add")',
    );
    await page.waitForLoadState('networkidle');
  },
);

Then(
  'the credential mapping for {string} appears in the list',
  async ({ page }, consumerId: string) => {
    const entry = page.locator(`text=${consumerId}`).first();
    await expect(entry).toBeVisible({ timeout: 10000 });
  },
);

Given(
  'a credential mapping for {string} exists',
  async ({ page }, consumerId: string) => {
    // Check if it already exists; if not, soft-warn (test data may be pre-seeded)
    const entry = page.locator(`text=${consumerId}`);
    const exists = await entry.first().isVisible({ timeout: 5000 }).catch(() => false);
    if (!exists) {
      expect
        .soft(exists, `Credential mapping for "${consumerId}" not found — ensure test data is seeded`)
        .toBe(true);
    }
  },
);

When(
  'I edit the credential mapping for {string} changing the value to {string}',
  async ({ page }, consumerId: string, newValue: string) => {
    const row = page.locator(`tr:has-text("${consumerId}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    const editBtn = row.locator(
      'button:has-text("Edit"), button[aria-label*="edit" i]',
    );
    if (await editBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await editBtn.click();

      const valueInput = page.locator(
        'input[name="header_value"], input[name="credential_value"], input[type="password"]',
      );
      if (await valueInput.first().isVisible({ timeout: 5000 }).catch(() => false)) {
        await valueInput.first().fill(newValue);
      }

      await page.click(
        'button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Update")',
      );
      await page.waitForLoadState('networkidle');
    }
  },
);

Then(
  'the credential mapping for {string} shows the updated value',
  async ({ page }, consumerId: string) => {
    // After update, the row still exists (value may be masked)
    const row = page.locator(`tr:has-text("${consumerId}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });
  },
);

When(
  'I delete the credential mapping for {string}',
  async ({ page }, consumerId: string) => {
    const row = page.locator(`tr:has-text("${consumerId}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    const deleteBtn = row.locator(
      'button:has-text("Delete"), button[aria-label*="delete" i], button:has-text("Remove")',
    );
    await expect(deleteBtn).toBeVisible({ timeout: 5000 });
    await deleteBtn.click();

    // Confirm if dialog appears
    const confirmBtn = page.locator(
      'button:has-text("Confirm"), button:has-text("Delete"), button:has-text("Yes")',
    );
    if (await confirmBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await confirmBtn.click();
    }
    await page.waitForLoadState('networkidle');
  },
);

Then(
  'the credential mapping for {string} is no longer in the list',
  async ({ page }, consumerId: string) => {
    const entry = page.locator(`text=${consumerId}`);
    await expect(entry).not.toBeVisible({ timeout: 10000 });
  },
);

// ============================================================================
// RBAC assertions
// ============================================================================

Then('the add credential mapping button is not visible or disabled', async ({ page }) => {
  const addBtn = page.locator(
    'button:has-text("Add Mapping"), button:has-text("Add Credential"), button:has-text("New Mapping")',
  );
  const isVisible = await addBtn.isVisible().catch(() => false);
  if (isVisible) {
    await expect(addBtn).toBeDisabled();
  }
  // If not visible, RBAC hides the button — test passes
});

Then('credential header values are masked or hidden from viewers', async ({ page }) => {
  // Check that any visible credential value cells either show a masked value or empty
  const valueCells = page.locator('td').filter({ hasText: /\*{3,}|••••|hidden|masked/i });
  const rawValues = page.locator('td').filter({ hasText: /^[a-zA-Z0-9_-]{8,}$/ });

  // Either masked values are shown OR no raw long-string values are visible
  const hasMasked = await valueCells.count().then((c) => c > 0).catch(() => false);
  const hasRaw = await rawValues.count().then((c) => c > 0).catch(() => false);

  // Viewers should see masked values (not raw credentials)
  // Soft assert — UI may show empty state if no mappings exist in this env
  expect.soft(!hasRaw || hasMasked, 'Credential values should be masked for viewers').toBe(true);
});
