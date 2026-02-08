/**
 * Common step definitions for STOA E2E Tests
 * Shared steps for navigation, authentication, and basic assertions
 *
 * Auth pattern: uses Playwright's storageState via the authSession fixture.
 * When a BDD step switches persona, authSession.switchPersona() creates a new
 * browser context with storageState (cookies + localStorage loaded natively).
 * Subsequent steps use authSession.page for the switched persona's session.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';
import { PERSONAS, PersonaKey } from '../fixtures/personas';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// AUTHENTICATION STEPS
// ============================================================================

Given('I am logged in as {string}', async ({ authSession }, personaName: string) => {
  const persona = PERSONAS[personaName as PersonaKey];
  if (!persona) {
    throw new Error(`Unknown persona: ${personaName}`);
  }
  await authSession.switchPersona(personaName as PersonaKey);
});

Given(
  'I am logged in as {string} from community {string}',
  async ({ authSession }, personaName: string, _community: string) => {
    const persona = PERSONAS[personaName as PersonaKey];
    if (!persona) {
      throw new Error(`Unknown persona: ${personaName}`);
    }
    await authSession.switchPersona(personaName as PersonaKey);
  },
);

Given(
  'I am logged in to Console as {string} from team {string}',
  async ({ authSession }, personaName: string, _team: string) => {
    const persona = PERSONAS[personaName as PersonaKey];
    if (!persona) {
      throw new Error(`Unknown persona: ${personaName}`);
    }
    await authSession.switchPersona(personaName as PersonaKey, URLS.console);
    await authSession.page.goto(URLS.console);
  },
);

Given(
  'I am logged in to Console as {string} platform admin',
  async ({ authSession }, personaName: string) => {
    await authSession.switchPersona(personaName as PersonaKey, URLS.console);
    await authSession.page.goto(URLS.console);
  },
);

// ============================================================================
// ACCESSIBILITY STEPS
// ============================================================================

Given('the STOA Portal is accessible', async ({ authSession }) => {
  const response = await authSession.page.goto(URLS.portal);
  expect(response?.status()).toBeLessThan(400);
});

Given('the STOA Console is accessible', async ({ authSession }) => {
  const response = await authSession.page.goto(URLS.console);
  expect(response?.status()).toBeLessThan(400);
});

// ============================================================================
// NAVIGATION STEPS
// ============================================================================

When('I navigate to page {string}', async ({ authSession }, path: string) => {
  await authSession.page.goto(path);
  await authSession.page.waitForLoadState('networkidle');
});

When('I navigate to the subscriptions page', async ({ authSession }) => {
  await authSession.page.goto('/subscriptions');
  await authSession.page.waitForLoadState('networkidle');
});

When('I navigate to my subscriptions', async ({ authSession }) => {
  await authSession.page.goto(`${URLS.portal}/subscriptions`);
  await authSession.page.waitForLoadState('networkidle');
});

// ============================================================================
// BASIC ASSERTIONS
// ============================================================================

Then('I should see the title {string}', async ({ authSession }, title: string) => {
  await expect(authSession.page.locator('h1').first()).toContainText(title);
});

Then('I receive an access denied error', async ({ authSession }) => {
  const page = authSession.page;
  const errorMessage = page.locator(
    'text=/access denied|forbidden|unauthorized|403|401|not found|error|failed/i',
  );
  const errorBanner = page.locator('[class*="error"], [class*="alert-danger"], [role="alert"]');

  const hasError =
    (await errorMessage.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await errorBanner.isVisible({ timeout: 3000 }).catch(() => false));

  if (!hasError) {
    const pageContent = await page.textContent('body');
    const hasNoData =
      !pageContent ||
      pageContent.includes('No APIs') ||
      pageContent.includes('error') ||
      pageContent.includes('Failed');
    expect(hasNoData || hasError).toBe(true);
  }
});
