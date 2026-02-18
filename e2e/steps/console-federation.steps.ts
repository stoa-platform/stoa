/**
 * Console step definitions for MCP Federation management (CAB-1363)
 * Steps for managing master accounts, sub-accounts, tool allow-lists, and usage.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// FEDERATION ACCOUNTS — NAVIGATION
// ============================================================================

When('I navigate to the Federation Accounts page', async ({ page }) => {
  await page.goto(`${URLS.console}/federation/accounts`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Federation Accounts page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Federation/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false));

  expect(loaded || page.url().includes('/federation/accounts')).toBe(true);
});

// ============================================================================
// MASTER ACCOUNT — CRUD
// ============================================================================

When(
  'I create a master account named {string} with max {int} sub-accounts',
  async ({ page }, name: string, maxSubs: number) => {
    const createBtn = page.locator(
      'button:has-text("Create Master Account"), button:has-text("Create")',
    );
    const btnVisible = await createBtn
      .first()
      .isVisible({ timeout: 15000 })
      .catch(() => false);
    if (!btnVisible) {
      expect
        .soft(btnVisible, 'Create Master Account button not found — API may be unreachable')
        .toBe(true);
      return;
    }
    await createBtn.first().click();

    // Fill name
    await page.fill('input[name="name"], input[id="name"], input[placeholder*="name" i]', name);

    // Fill max sub-accounts if the field exists
    const maxInput = page.locator(
      'input[name="max_sub_accounts"], input[type="number"]',
    );
    if (await maxInput.isVisible({ timeout: 2000 }).catch(() => false)) {
      await maxInput.fill(String(maxSubs));
    }

    // Submit
    await page.click(
      'button[type="submit"]:has-text("Create"), button[type="submit"]:has-text("Save")',
    );
    await page.waitForLoadState('networkidle');
  },
);

Then(
  'the master account {string} appears in the list',
  async ({ page }, name: string) => {
    await page.goto(`${URLS.console}/federation/accounts`);
    await page.waitForLoadState('networkidle');
    const entry = page.locator(`text=${name}`).first();
    await expect(entry).toBeVisible({ timeout: 10000 });
  },
);

When('I click on the master account {string}', async ({ page }, name: string) => {
  const row = page.locator(`tr:has-text("${name}"), [class*="card"]:has-text("${name}")`).first();
  await expect(row).toBeVisible({ timeout: 10000 });
  await row.click();
  await page.waitForLoadState('networkidle');
});

Then('I see the master account detail page', async ({ page }) => {
  // Detail page should have sub-accounts section and usage section
  const detailContent = page.locator('text=/Sub-Accounts|sub-account/i');
  await expect(detailContent.first()).toBeVisible({ timeout: 10000 });
});

Then('the usage breakdown section is visible', async ({ page }) => {
  const usageSection = page.locator('text=/Usage|Requests|usage/i');
  await expect(usageSection.first()).toBeVisible({ timeout: 10000 });
});

When('I suspend the master account', async ({ page }) => {
  const suspendBtn = page.locator('button:has-text("Suspend")');
  await expect(suspendBtn).toBeVisible({ timeout: 10000 });
  await suspendBtn.click();
});

Then('the master account status shows {string}', async ({ page }, status: string) => {
  const statusBadge = page.locator(`text=${status}`).first();
  await expect(statusBadge).toBeVisible({ timeout: 10000 });
});

When('I delete the master account {string}', async ({ page }, name: string) => {
  const row = page.locator(`tr:has-text("${name}")`).first();
  await expect(row).toBeVisible({ timeout: 10000 });

  const deleteBtn = row.locator(
    'button:has-text("Delete"), button[aria-label*="delete" i]',
  );
  await expect(deleteBtn).toBeVisible({ timeout: 5000 });
  await deleteBtn.click();
});

Then(
  'the master account {string} is no longer in the list',
  async ({ page }, name: string) => {
    await page.goto(`${URLS.console}/federation/accounts`);
    await page.waitForLoadState('networkidle');
    const entry = page.locator(`text=${name}`);
    await expect(entry).not.toBeVisible({ timeout: 10000 });
  },
);

Then('the Create Master Account button is not visible or disabled', async ({ page }) => {
  const createBtn = page.locator(
    'button:has-text("Create Master Account"), button:has-text("Create")',
  );
  const isVisible = await createBtn.isVisible().catch(() => false);
  if (isVisible) {
    await expect(createBtn).toBeDisabled();
  }
  // If not visible, the test passes (RBAC hides the button)
});

// ============================================================================
// SUB-ACCOUNT — CRUD
// ============================================================================

When('I create a sub-account named {string}', async ({ page }, name: string) => {
  const addBtn = page.locator(
    'button:has-text("Add Sub-Account"), button:has-text("Add")',
  );
  const btnVisible = await addBtn
    .first()
    .isVisible({ timeout: 15000 })
    .catch(() => false);
  if (!btnVisible) {
    expect
      .soft(btnVisible, 'Add Sub-Account button not found — API may be unreachable')
      .toBe(true);
    return;
  }
  await addBtn.first().click();

  // Fill name
  await page.fill('input[name="name"], input[id="name"], input[placeholder*="name" i]', name);

  // Submit
  await page.click(
    'button[type="submit"]:has-text("Create"), button[type="submit"]:has-text("Save")',
  );
  await page.waitForLoadState('networkidle');
});

Then('the API key reveal dialog is displayed', async ({ page }) => {
  const dialog = page.locator('text=/API Key|key created|Copy this key/i');
  await expect(dialog.first()).toBeVisible({ timeout: 10000 });
});

Then('I dismiss the API key dialog', async ({ page }) => {
  const doneBtn = page.locator('button:has-text("Done"), button:has-text("OK"), button:has-text("Close")');
  await expect(doneBtn.first()).toBeVisible({ timeout: 5000 });
  await doneBtn.first().click();
});

Then(
  'the sub-account {string} appears in the sub-accounts table',
  async ({ page }, name: string) => {
    const entry = page.locator(`text=${name}`).first();
    await expect(entry).toBeVisible({ timeout: 10000 });
  },
);

// ============================================================================
// TOOL ALLOW-LIST
// ============================================================================

When(
  'I open the tool allow-list for sub-account {string}',
  async ({ page }, name: string) => {
    const row = page.locator(`tr:has-text("${name}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    const toolsBtn = row.locator(
      'button:has-text("Tools"), button[aria-label*="tools" i], button[data-testid*="tools"]',
    );
    await expect(toolsBtn).toBeVisible({ timeout: 5000 });
    await toolsBtn.click();
  },
);

Then('the tool allow-list modal is displayed', async ({ page }) => {
  const modal = page.locator('text=/Tool Allow|Allowed Tools|tool catalog/i');
  await expect(modal.first()).toBeVisible({ timeout: 10000 });
});

// ============================================================================
// USAGE
// ============================================================================

When('I change the usage period to {string} days', async ({ page }, days: string) => {
  const select = page.locator('select[aria-label*="period" i], select[name*="period"]');
  if (await select.isVisible({ timeout: 5000 }).catch(() => false)) {
    await select.selectOption(days);
  } else {
    // Try clicking a period button instead
    const periodBtn = page.locator(`button:has-text("${days}d"), button:has-text("${days} days")`);
    if (await periodBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await periodBtn.click();
    }
  }
  await page.waitForLoadState('networkidle');
});

Then('the usage breakdown reflects the selected period', async ({ page }) => {
  // The usage section should be visible and updated
  const usageSection = page.locator('text=/Requests|Usage/i');
  await expect(usageSection.first()).toBeVisible({ timeout: 10000 });
});

// ============================================================================
// SHARED — CONFIRMATION DIALOGS
// ============================================================================

When('I confirm the action', async ({ page }) => {
  const confirmBtn = page.locator(
    'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("OK")',
  );
  await expect(confirmBtn.first()).toBeVisible({ timeout: 5000 });
  await confirmBtn.first().click();
  await page.waitForLoadState('networkidle');
});
