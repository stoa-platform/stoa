// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Extended Playwright test with custom fixtures for STOA E2E
 */

import { test as base } from 'playwright-bdd';
import { expect, Page, BrowserContext } from '@playwright/test';
import { PERSONAS, PersonaKey, Persona, getAuthStatePath } from './personas';
import * as fs from 'fs';

// URLs
const PORTAL_URL = process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev';
const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';

/**
 * Custom test fixtures
 */
export type TestFixtures = {
  persona: Persona | null;
  portalPage: Page;
  consolePage: Page;
  authenticatedContext: BrowserContext;
};

/**
 * Extended test with STOA-specific fixtures
 */
export const test = base.extend<TestFixtures>({
  // Current persona (set via step definitions)
  persona: [null, { option: true }],

  // Portal page fixture
  portalPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      baseURL: PORTAL_URL,
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  // Console page fixture
  consolePage: async ({ browser }, use) => {
    const context = await browser.newContext({
      baseURL: CONSOLE_URL,
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  // Authenticated context (loaded from storage state)
  authenticatedContext: async ({ browser }, use) => {
    // Default to parzival if no persona specified
    const personaKey: PersonaKey = 'parzival';
    const authStatePath = getAuthStatePath(personaKey);

    let context;
    if (fs.existsSync(authStatePath)) {
      context = await browser.newContext({
        storageState: authStatePath,
      });
    } else {
      console.warn(`Auth state not found for ${personaKey}, using fresh context`);
      context = await browser.newContext();
    }

    await use(context);
    await context.close();
  },
});

/**
 * Helper to load authenticated context for a specific persona
 */
export async function loadPersonaContext(
  browser: any,
  personaKey: PersonaKey,
  baseURL?: string
): Promise<BrowserContext> {
  const persona = PERSONAS[personaKey];
  const authStatePath = getAuthStatePath(personaKey);

  const options: any = {
    baseURL: baseURL || (persona.defaultApp === 'portal' ? PORTAL_URL : CONSOLE_URL),
  };

  if (fs.existsSync(authStatePath)) {
    options.storageState = authStatePath;
  } else {
    console.warn(`Auth state not found for ${personaKey}`);
  }

  return browser.newContext(options);
}

/**
 * Re-export expect for convenience
 */
export { expect };

/**
 * URLs for use in tests
 */
export const URLS = {
  portal: PORTAL_URL,
  console: CONSOLE_URL,
  gateway: GATEWAY_URL,
};
