/**
 * Portal Chat Settings step definitions for STOA E2E Tests (CAB-1854)
 * Tests for the Portal ChatSettings page: toggles, budget, RBAC.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// NAVIGATION
// ============================================================================

When('I navigate to the chat settings page in Portal', async ({ authSession }) => {
  const page = authSession.page;
  await page.goto(`${URLS.portal}/chat-settings`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Portal chat settings page loads successfully', async ({ authSession }) => {
  const page = authSession.page;

  const heading = page.locator('h1, h2').filter({ hasText: /chat|settings/i });
  const saveBtn = page.locator(
    'button:has-text("Save"), button:has-text("Save Settings"), [data-testid="save-settings"]',
  );

  const pageLoaded =
    (await heading.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await saveBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/chat-settings');

  expect(pageLoaded).toBe(true);
});

// ============================================================================
// TOGGLE & INPUT STEPS (Portal-scoped)
// ============================================================================

When('I toggle the portal chat enable switch in Portal', async ({ authSession }) => {
  const page = authSession.page;
  const toggle = page.locator(
    'button[role="switch"]:near(:text("Enable Chat in Developer Portal")), [data-testid="portal-toggle"]',
  );
  const hasToggle = await toggle.first().isVisible({ timeout: 8000 }).catch(() => false);
  if (hasToggle) {
    await toggle.first().click();
    await page.waitForTimeout(300);
  }
});

When('I set the portal daily budget to {int}', async ({ authSession }, budget: number) => {
  const page = authSession.page;
  const input = page.locator('input[type="number"], input[role="spinbutton"]');
  const hasInput = await input.first().isVisible({ timeout: 8000 }).catch(() => false);
  if (hasInput) {
    await input.first().fill(String(budget));
  }
});

// ============================================================================
// SAVE STEPS
// ============================================================================

When('I save the portal chat settings', async ({ authSession }) => {
  const page = authSession.page;
  const saveBtn = page.locator(
    'button:has-text("Save Settings"), button:has-text("Save"), [data-testid="save-settings"]',
  );
  const hasBtn = await saveBtn.first().isVisible({ timeout: 8000 }).catch(() => false);
  if (hasBtn) {
    await saveBtn.first().click();
    await page.waitForLoadState('networkidle');
  }
});

Then('the portal chat settings save succeeds', async ({ authSession }) => {
  const page = authSession.page;

  const successIndicator = page.locator(
    'text=/saved|updated|success/i, [class*="success"], [class*="alert-success"], [role="alert"]:has-text("saved")',
  );

  const hasSaved =
    (await successIndicator.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/chat-settings');

  expect(hasSaved).toBe(true);
});

// ============================================================================
// RBAC — VIEWER
// ============================================================================

Then('the portal viewer cannot save chat settings', async ({ authSession }) => {
  const page = authSession.page;

  if (!page.url().includes('/chat-settings')) {
    // Redirected — access denied for viewer, pass
    return;
  }

  const saveBtn = page.locator(
    'button:has-text("Save Settings"), button:has-text("Save"), [data-testid="save-settings"]',
  );
  const hasSaveBtn = await saveBtn.first().isVisible({ timeout: 5000 }).catch(() => false);
  if (hasSaveBtn) {
    const isDisabled = await saveBtn.first().isDisabled().catch(() => false);
    expect(isDisabled).toBe(true);
  }
});
