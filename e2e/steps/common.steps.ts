// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Common step definitions for STOA E2E Tests
 * Shared steps for navigation, authentication, and basic assertions
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';
import { PERSONAS, PersonaKey, getAuthStatePath } from '../fixtures/personas';
import * as fs from 'fs';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// AUTHENTICATION STEPS
// ============================================================================

Given('I am logged in as {string}', async ({ page, context }, personaName: string) => {
  const persona = PERSONAS[personaName as PersonaKey];
  if (!persona) {
    throw new Error(`Unknown persona: ${personaName}`);
  }

  const authStatePath = getAuthStatePath(personaName as PersonaKey);
  if (fs.existsSync(authStatePath)) {
    const storageState = JSON.parse(fs.readFileSync(authStatePath, 'utf-8'));

    if (storageState.cookies) {
      await context.addCookies(storageState.cookies);
    }

    if (storageState.origins?.[0]?.localStorage) {
      const baseURL = persona.defaultApp === 'portal' ? URLS.portal : URLS.console;
      await page.goto(baseURL);
      for (const item of storageState.origins[0].localStorage) {
        await page.evaluate(({ key, value }) => localStorage.setItem(key, value), item);
      }
    }
  }
});

Given('I am logged in as {string} from community {string}', async ({ page, context }, personaName: string, _community: string) => {
  const persona = PERSONAS[personaName as PersonaKey];
  if (!persona) {
    throw new Error(`Unknown persona: ${personaName}`);
  }

  const authStatePath = getAuthStatePath(personaName as PersonaKey);
  if (fs.existsSync(authStatePath)) {
    const storageState = JSON.parse(fs.readFileSync(authStatePath, 'utf-8'));
    if (storageState.cookies) {
      await context.addCookies(storageState.cookies);
    }
  }
});

Given('I am logged in to Console as {string} from team {string}', async ({ page, context }, personaName: string, _team: string) => {
  const persona = PERSONAS[personaName as PersonaKey];
  if (!persona) {
    throw new Error(`Unknown persona: ${personaName}`);
  }

  const authStatePath = getAuthStatePath(personaName as PersonaKey);
  if (fs.existsSync(authStatePath)) {
    const storageState = JSON.parse(fs.readFileSync(authStatePath, 'utf-8'));
    if (storageState.cookies) {
      await context.addCookies(storageState.cookies);
    }
  }

  await page.goto(URLS.console);
});

Given('I am logged in to Console as {string} platform admin', async ({ page, context }, personaName: string) => {
  const authStatePath = getAuthStatePath(personaName as PersonaKey);
  if (fs.existsSync(authStatePath)) {
    const storageState = JSON.parse(fs.readFileSync(authStatePath, 'utf-8'));
    if (storageState.cookies) {
      await context.addCookies(storageState.cookies);
    }
  }

  await page.goto(URLS.console);
});

// ============================================================================
// ACCESSIBILITY STEPS
// ============================================================================

Given('the STOA Portal is accessible', async ({ page }) => {
  const response = await page.goto(URLS.portal);
  expect(response?.status()).toBeLessThan(400);
});

Given('the STOA Console is accessible', async ({ page }) => {
  const response = await page.goto(URLS.console);
  expect(response?.status()).toBeLessThan(400);
});

// ============================================================================
// NAVIGATION STEPS
// ============================================================================

When('I navigate to page {string}', async ({ page }, path: string) => {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
});

When('I navigate to the subscriptions page', async ({ page }) => {
  await page.goto('/subscriptions');
  await page.waitForLoadState('networkidle');
});

When('I navigate to my subscriptions', async ({ page }) => {
  await page.goto(`${URLS.portal}/subscriptions`);
  await page.waitForLoadState('networkidle');
});

// ============================================================================
// BASIC ASSERTIONS
// ============================================================================

Then('I should see the title {string}', async ({ page }, title: string) => {
  await expect(page.locator('h1').first()).toContainText(title);
});

Then('I receive an access denied error', async ({ page }) => {
  const errorMessage = page.locator('text=/access denied|forbidden|unauthorized|403|401/i');
  await expect(errorMessage).toBeVisible({ timeout: 10000 });
});
