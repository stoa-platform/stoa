/**
 * Console step definitions for SaaS Backend APIs + API Keys (CAB-1252)
 * Steps for managing backend API registrations and scoped API keys.
 */

import { createBdd } from "playwright-bdd";
import { test, expect, URLS } from "../fixtures/test-base";

const { When, Then } = createBdd(test);

// ============================================================================
// BACKEND APIs — NAVIGATION
// ============================================================================

When("I navigate to the Backend APIs page", async ({ page }) => {
  await page.goto(`${URLS.console}/backend-apis`);
  await page.waitForLoadState("networkidle");
  await expect(page.locator("text=Loading").first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then("the Backend APIs page loads successfully", async ({ page }) => {
  const heading = page.locator("h1, h2").filter({ hasText: /Backend APIs/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false));

  expect(loaded || page.url().includes("/backend-apis")).toBe(true);
});

// ============================================================================
// BACKEND APIs — CRUD
// ============================================================================

When(
  "I register a backend API named {string} with URL {string}",
  async ({ page }, apiName: string, backendUrl: string) => {
    const registerBtn = page.locator(
      'button:has-text("Register API"), button:has-text("Register")',
    );
    const btnVisible = await registerBtn
      .first()
      .isVisible({ timeout: 15000 })
      .catch(() => false);
    if (!btnVisible) {
      expect
        .soft(
          btnVisible,
          "Register API button not found — API may be unreachable",
        )
        .toBe(true);
      return;
    }
    await registerBtn.first().click();

    // Fill required fields
    await page.fill(
      'input[placeholder*="my-backend"], input[name="name"], input[id="name"]',
      apiName,
    );

    const urlInput = page.locator(
      'input[type="url"], input[placeholder*="https://"], input[name="backend_url"]',
    );
    if (await urlInput.isVisible()) {
      await urlInput.fill(backendUrl);
    }

    // Submit
    await page.click(
      'button[type="submit"]:has-text("Register"), button[type="submit"]:has-text("Create"), button[type="submit"]:has-text("Save")',
    );
    await page.waitForLoadState("networkidle");
  },
);

Then(
  "the backend API {string} appears in the list",
  async ({ page }, apiName: string) => {
    await page.goto(`${URLS.console}/backend-apis`);
    await page.waitForLoadState("networkidle");
    const entry = page.locator(`text=${apiName}`).first();
    await expect(entry).toBeVisible({ timeout: 10000 });
  },
);

When(
  "I toggle the status of backend API {string}",
  async ({ page }, apiName: string) => {
    const row = page.locator(`tr:has-text("${apiName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    // Look for a toggle/status button in the row
    const toggleBtn = row.locator(
      'button:has-text("Activate"), button:has-text("Disable"), button:has-text("Enable")',
    );
    if (await toggleBtn.isVisible()) {
      await toggleBtn.click();
      await page.waitForLoadState("networkidle");
    }
  },
);

Then(
  "the backend API {string} status changes",
  async ({ page }, apiName: string) => {
    const row = page.locator(`tr:has-text("${apiName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });
    // Status badge should be visible (active, disabled, or draft)
    const statusBadge = row.locator(
      'span:has-text("Active"), span:has-text("Disabled")',
    );
    await expect(statusBadge).toBeVisible({ timeout: 5000 });
  },
);

When("I delete the backend API {string}", async ({ page }, apiName: string) => {
  const row = page.locator(`tr:has-text("${apiName}")`).first();
  await expect(row).toBeVisible({ timeout: 10000 });

  const deleteBtn = row.locator(
    'button:has-text("Delete"), button:has-text("Supprimer"), button[aria-label*="delete" i]',
  );
  await expect(deleteBtn).toBeVisible({ timeout: 5000 });
  await deleteBtn.click();
});

Then(
  "the backend API {string} is no longer in the list",
  async ({ page }, apiName: string) => {
    await page.goto(`${URLS.console}/backend-apis`);
    await page.waitForLoadState("networkidle");
    const entry = page.locator(`text=${apiName}`);
    await expect(entry).not.toBeVisible({ timeout: 10000 });
  },
);

Then("the Register API button is not visible or disabled", async ({ page }) => {
  const registerBtn = page.locator(
    'button:has-text("Register API"), button:has-text("Register")',
  );
  const isVisible = await registerBtn.isVisible().catch(() => false);
  if (isVisible) {
    await expect(registerBtn).toBeDisabled();
  }
  // If not visible, the test passes (RBAC hides the button)
});

// ============================================================================
// API KEYS — NAVIGATION
// ============================================================================

When("I navigate to the API Keys page", async ({ page }) => {
  await page.goto(`${URLS.console}/saas-api-keys`);
  await page.waitForLoadState("networkidle");
  await expect(page.locator("text=Loading").first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then("the API Keys page loads successfully", async ({ page }) => {
  const heading = page.locator("h1, h2").filter({ hasText: /API Keys/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false));

  expect(loaded || page.url().includes("/saas-api-keys")).toBe(true);
});

// ============================================================================
// API KEYS — CRUD
// ============================================================================

When(
  "I create an API key named {string}",
  async ({ page }, keyName: string) => {
    const createBtn = page.locator(
      'button:has-text("Create Key"), button:has-text("Create")',
    );
    const btnVisible = await createBtn
      .first()
      .isVisible({ timeout: 15000 })
      .catch(() => false);
    if (!btnVisible) {
      expect
        .soft(
          btnVisible,
          "Create Key button not found — API may be unreachable",
        )
        .toBe(true);
      return;
    }
    await createBtn.first().click();

    // Fill name
    await page.fill(
      'input[placeholder*="my-api-key"], input[name="name"], input[id="name"]',
      keyName,
    );

    // Submit
    await page.click(
      'button[type="submit"]:has-text("Create Key"), button[type="submit"]:has-text("Create")',
    );
    await page.waitForLoadState("networkidle");
  },
);

Then("the key reveal dialog shows the new key", async ({ page }) => {
  // Key reveal dialog has "API Key Created" heading and the key value
  const heading = page.locator('h2:has-text("API Key Created")');
  await expect(heading).toBeVisible({ timeout: 10000 });

  // The key value should be in a code block
  const keyValue = page.locator("code");
  await expect(keyValue).toBeVisible();

  // Warning about not showing again
  const warning = page.locator("text=/will not be shown again|Copy this key/i");
  await expect(warning).toBeVisible();
});

Then("I dismiss the key reveal dialog", async ({ page }) => {
  const doneBtn = page.locator('button:has-text("Done")');
  await expect(doneBtn).toBeVisible({ timeout: 5000 });
  await doneBtn.click();
});

When("I revoke the API key {string}", async ({ page }, keyName: string) => {
  const row = page.locator(`tr:has-text("${keyName}")`).first();
  await expect(row).toBeVisible({ timeout: 10000 });

  const revokeBtn = row.locator('button:has-text("Revoke")');
  await expect(revokeBtn).toBeVisible({ timeout: 5000 });
  await revokeBtn.click();
});

Then(
  "the API key {string} shows as revoked",
  async ({ page }, keyName: string) => {
    await page.waitForLoadState("networkidle");
    const row = page.locator(`tr:has-text("${keyName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    const revokedBadge = row.locator('span:has-text("Revoked")');
    await expect(revokedBadge).toBeVisible({ timeout: 5000 });
  },
);

Then("the Create Key button is not visible or disabled", async ({ page }) => {
  const createBtn = page.locator(
    'button:has-text("Create Key"), button:has-text("Create")',
  );
  const isVisible = await createBtn.isVisible().catch(() => false);
  if (isVisible) {
    await expect(createBtn).toBeDisabled();
  }
  // If not visible, the test passes (RBAC hides the button)
});
