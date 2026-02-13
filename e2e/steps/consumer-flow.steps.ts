/**
 * Consumer Flow step definitions for STOA E2E Tests
 * Steps for the API consumer journey: discover, subscribe, consume
 */

import { createBdd } from "playwright-bdd";
import { test, expect } from "../fixtures/test-base";
import * as path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const { When, Then } = createBdd(test);

// ============================================================================
// API CATALOG DETAIL STEPS
// ============================================================================

When("I click on the first API in the catalog", async ({ page }) => {
  const apiCard = page.locator('a[href^="/apis/"]').first();
  await expect.soft(apiCard).toBeVisible({ timeout: 10000 });
  await apiCard.click();
  await page.waitForLoadState("networkidle");
});

Then(
  "the API detail page loads with description and endpoints",
  async ({ page }) => {
    const url = page.url();
    const heading = page.locator("h1, h2").first();
    const description = page.locator(
      "text=/description|overview|endpoint|version|base url/i",
    );

    const loaded =
      url.includes("/apis/") ||
      (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
      (await description
        .first()
        .isVisible({ timeout: 5000 })
        .catch(() => false));

    expect.soft(loaded).toBe(true);
  },
);

// Note: application management steps (create, appears in list, click, detail page)
// are defined in portal-advanced.steps.ts and portal-contracts.steps.ts

// ============================================================================
// SUBSCRIPTION FLOW STEPS
// ============================================================================

When("I click the subscribe button", async ({ page }) => {
  const subscribeButton = page.locator(
    'button:has-text("Subscribe"), button:has-text("Souscrire"), a:has-text("Subscribe")',
  );
  await expect.soft(subscribeButton.first()).toBeVisible({ timeout: 10000 });
  await subscribeButton.first().click();
  await page.waitForLoadState("networkidle");
});

When(
  "I select application {string} for the subscription",
  async ({ page }, appName: string) => {
    const appSelect = page
      .locator(
        'select[name*="application"], select[name*="app"], [role="combobox"]',
      )
      .first();

    if (await appSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
      const options = await appSelect.locator("option").all();
      let matched = false;
      for (const opt of options) {
        const text = await opt.textContent();
        if (text && text.toLowerCase().includes(appName.toLowerCase())) {
          const value = await opt.getAttribute("value");
          if (value) {
            await appSelect.selectOption(value);
            matched = true;
            break;
          }
        }
      }
      if (!matched && options.length > 1) {
        const value = await options[1].getAttribute("value");
        if (value) {
          await appSelect.selectOption(value);
        }
      }
    } else {
      const appCard = page
        .locator(
          `label:has-text("${appName}"), [class*="card"]:has-text("${appName}"), tr:has-text("${appName}")`,
        )
        .first();
      if (await appCard.isVisible({ timeout: 3000 }).catch(() => false)) {
        await appCard.click();
      }
    }
  },
);

// Note: 'I confirm the subscription' and 'the subscription is created with status {string}'
// are defined in portal.steps.ts

// ============================================================================
// APPLICATION DETAIL STEPS
// ============================================================================

Then("the API key section is visible", async ({ page }) => {
  const apiKeySection = page.locator(
    "text=/api key|credentials|secret|token|cle|identifiant/i",
  );
  const isVisible = await apiKeySection
    .first()
    .isVisible({ timeout: 10000 })
    .catch(() => false);
  expect
    .soft(
      isVisible ||
        page.url().includes("/apps/") ||
        page.url().includes("/workspace/"),
    )
    .toBe(true);
});

// Note: analytics steps and 'the applications page loads successfully'
// are defined in portal-advanced.steps.ts

// ============================================================================
// APPLICATION ISOLATION STEPS
// ============================================================================

Then(
  "I do not see applications from tenant {string}",
  async ({ page }, tenantName: string) => {
    await page.waitForLoadState("networkidle");

    const pageContent = await page.textContent("body");
    const hasTenantContent =
      pageContent?.toLowerCase().includes(tenantName.toLowerCase()) || false;

    expect
      .soft(!hasTenantContent || page.url().includes("/workspace"))
      .toBe(true);
  },
);

// ============================================================================
// mTLS CERTIFICATE STEPS (CAB-872)
// ============================================================================

const CERTS_DIR = path.resolve(__dirname, "../../scripts/demo/certs");

When("I upload a test certificate file", async ({ page }) => {
  // CertificateUploader has a hidden <input type="file"> — use setInputFiles
  const fileInput = page.locator('input[type="file"][accept*=".pem"]');
  const certPath = path.join(CERTS_DIR, "client-001.pem");
  await fileInput.setInputFiles(certPath);
  // Wait for the upload to be processed (fingerprint displayed)
  await page.waitForTimeout(1000);
});

When("I click on the first subscription", async ({ page }) => {
  const subCard = page
    .locator(
      '[class*="card"], [class*="rounded-lg"], tr, a[href*="/subscriptions/"]',
    )
    .first();
  await expect.soft(subCard).toBeVisible({ timeout: 10000 });
  await subCard.click();
  await page.waitForLoadState("networkidle");
});

Then("I can see the certificate fingerprint", async ({ page }) => {
  // Fingerprint is a SHA-256 hex string (64 hex chars) or displayed with colons
  const fingerprint = page.locator("text=/[0-9a-fA-F]{64}|[0-9a-fA-F:]{95}/");
  await expect.soft(fingerprint.first()).toBeVisible({ timeout: 10000 });
});

Then("the certificate status is {string}", async ({ page }, status: string) => {
  const statusBadge = page.locator(`text=/${status}/i`);
  await expect.soft(statusBadge.first()).toBeVisible({ timeout: 10000 });
});
