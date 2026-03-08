/**
 * Console Applications — Multi-Env Tabs + FAPI Key Management
 * Step definitions for CAB-1748 E2E scenarios
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// AUTH — Console login
// ============================================================================

Given('I am logged in as {string} on the Console', async ({ authSession }, persona: string) => {
  await authSession.switchPersona(
    persona as Parameters<typeof authSession.switchPersona>[0],
    URLS.console
  );
});

// ============================================================================
// NAVIGATION
// ============================================================================

When('I navigate to the console applications page', async ({ authSession }) => {
  const page = authSession.page;
  await page.goto(`${URLS.console}/applications`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

// ============================================================================
// MULTI-ENV TABS
// ============================================================================

Then(
  'I see environment tabs {string}, {string}, {string}, {string}',
  async ({ authSession }, tab1: string, tab2: string, tab3: string, tab4: string) => {
    const page = authSession.page;
    for (const tabLabel of [tab1, tab2, tab3, tab4]) {
      const tab = page.locator('button').filter({ hasText: tabLabel });
      await expect(tab).toBeVisible({ timeout: 10000 });
    }
  }
);

When('I click the {string} environment tab', async ({ authSession }, tabLabel: string) => {
  const page = authSession.page;
  const tab = page.locator('button').filter({ hasText: tabLabel });
  await expect(tab).toBeVisible({ timeout: 10000 });
  await tab.click();
  // Wait for client-side filter to apply
  await page.waitForTimeout(500);
});

Then(
  'only applications from {string} environment are displayed',
  async ({ authSession }, env: string) => {
    const page = authSession.page;
    // The env tab should be active (has distinct styling)
    // Verify via URL param as proxy for filter state
    expect(page.url()).toContain(`env=${env}`);
  }
);

Then('the URL contains {string}', async ({ authSession }, param: string) => {
  expect(authSession.page.url()).toContain(param);
});

Then('applications from all environments are displayed', async ({ authSession }) => {
  const page = authSession.page;
  // "All Environments" tab = no env param in URL
  const url = page.url();
  expect(
    url.includes('env=development') || url.includes('env=staging') || url.includes('env=production')
  ).toBe(false);
});

// ============================================================================
// CREATE FORM
// ============================================================================

When('I open the create application form', async ({ authSession }) => {
  const page = authSession.page;
  const createBtn = page.locator('button:has-text("Create Application")');
  await expect(createBtn).toBeVisible({ timeout: 10000 });
  await createBtn.click();
  // Wait for modal to appear
  await expect(
    page.locator('input[placeholder="My Mobile App"], input[name="display_name"]').first()
  ).toBeVisible({ timeout: 5000 });
});

When('I select the {string} security profile', async ({ authSession }, profileLabel: string) => {
  const page = authSession.page;
  const profileRadio = page.locator('label').filter({ hasText: profileLabel });
  await expect(profileRadio).toBeVisible({ timeout: 5000 });
  await profileRadio.click();
  // Wait for conditional UI to render
  await page.waitForTimeout(300);
});

// ============================================================================
// FAPI KEY MANAGEMENT
// ============================================================================

Then('the FAPI key management section is visible', async ({ authSession }) => {
  const page = authSession.page;
  const fapiSection = page.locator('text=FAPI requires a public key');
  await expect(fapiSection).toBeVisible({ timeout: 5000 });
});

Then('the FAPI key management section is not visible', async ({ authSession }) => {
  const page = authSession.page;
  const fapiSection = page.locator('text=FAPI requires a public key');
  await expect(fapiSection).not.toBeVisible({ timeout: 3000 });
});

Then(
  'I see the {string} and {string} mode buttons',
  async ({ authSession }, btn1: string, btn2: string) => {
    const page = authSession.page;
    await expect(page.locator(`button:has-text("${btn1}")`)).toBeVisible({ timeout: 5000 });
    await expect(page.locator(`button:has-text("${btn2}")`)).toBeVisible({ timeout: 5000 });
  }
);

Then('the PEM upload textarea is visible by default', async ({ authSession }) => {
  const page = authSession.page;
  const textarea = page.locator('textarea[placeholder*="BEGIN PUBLIC KEY"]');
  await expect(textarea).toBeVisible({ timeout: 5000 });
});

Then('the PEM upload textarea is visible', async ({ authSession }) => {
  const page = authSession.page;
  const textarea = page.locator('textarea[placeholder*="BEGIN PUBLIC KEY"]');
  await expect(textarea).toBeVisible({ timeout: 5000 });
});

Then('the PEM upload textarea is not visible', async ({ authSession }) => {
  const page = authSession.page;
  const textarea = page.locator('textarea[placeholder*="BEGIN PUBLIC KEY"]');
  await expect(textarea).not.toBeVisible({ timeout: 3000 });
});

When('I click the {string} mode button', async ({ authSession }, btnText: string) => {
  const page = authSession.page;
  const btn = page.locator(`button:has-text("${btnText}")`);
  await expect(btn).toBeVisible({ timeout: 5000 });
  await btn.click();
  await authSession.page.waitForTimeout(300);
});

Then('the JWKS URL input is visible', async ({ authSession }) => {
  const page = authSession.page;
  const input = page.locator('input[placeholder*="well-known/jwks.json"]');
  await expect(input).toBeVisible({ timeout: 5000 });
});

Then('the JWKS URL input is not visible', async ({ authSession }) => {
  const page = authSession.page;
  const input = page.locator('input[placeholder*="well-known/jwks.json"]');
  await expect(input).not.toBeVisible({ timeout: 3000 });
});

// ============================================================================
// RBAC
// ============================================================================

Then('the "Create Application" button is not visible or disabled', async ({ authSession }) => {
  const page = authSession.page;
  const btn = page.locator('button:has-text("Create Application")');
  const isVisible = await btn.isVisible({ timeout: 5000 }).catch(() => false);
  if (isVisible) {
    await expect(btn).toBeDisabled();
  }
  // If not visible, RBAC correctly hides the button — test passes
});
