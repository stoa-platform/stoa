/**
 * Extended Playwright test with custom fixtures for STOA E2E
 *
 * Auth strategy: uses Playwright's storageState pattern for session restoration.
 * The `authSession` fixture holds a mutable { page, context } pair that auth steps
 * can swap via switchPersona() when a BDD step requires a different persona.
 */

import { test as base } from 'playwright-bdd';
import { expect, Page, BrowserContext, Browser } from '@playwright/test';
import { PERSONAS, PersonaKey, Persona, getAuthStatePath } from './personas';
import * as fs from 'fs';

// URLs
const PORTAL_URL = process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev';
const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';

/**
 * Mutable auth session that can be swapped when BDD steps switch personas.
 */
export interface AuthSession {
  page: Page;
  context: BrowserContext;
  switchPersona: (personaKey: PersonaKey, navigateUrl?: string) => Promise<void>;
}

/**
 * Restore sessionStorage for a persona after navigation.
 * Playwright's storageState only captures cookies + localStorage natively.
 * react-oidc-context stores OIDC tokens in sessionStorage, so we restore them manually.
 */
async function restoreSessionStorage(
  page: Page,
  personaKey: PersonaKey,
  navigateUrl: string,
): Promise<void> {
  const authStatePath = getAuthStatePath(personaKey);
  if (!fs.existsSync(authStatePath)) return;

  const stateData = JSON.parse(fs.readFileSync(authStatePath, 'utf-8'));
  if (!stateData.sessionStorage || Object.keys(stateData.sessionStorage).length === 0) return;

  // Navigate to target URL first so we have a valid origin for sessionStorage
  if (!page.url().startsWith('http')) {
    await page.goto(navigateUrl);
  }

  await page.evaluate((data: Record<string, string>) => {
    for (const [key, value] of Object.entries(data)) {
      sessionStorage.setItem(key, value);
    }
  }, stateData.sessionStorage);
}

/**
 * Create a new authenticated browser context using Playwright's storageState.
 * This is the recommended Playwright pattern: cookies + localStorage are loaded
 * natively by the browser context at creation time.
 */
export async function createAuthenticatedContext(
  browser: Browser,
  personaKey: PersonaKey,
  baseURL?: string,
): Promise<{ context: BrowserContext; page: Page }> {
  const persona = PERSONAS[personaKey];
  const authStatePath = getAuthStatePath(personaKey);
  const targetBaseURL =
    baseURL || (persona.defaultApp === 'portal' ? PORTAL_URL : CONSOLE_URL);

  const contextOptions: Parameters<Browser['newContext']>[0] = { baseURL: targetBaseURL };

  if (fs.existsSync(authStatePath)) {
    contextOptions.storageState = authStatePath;
  } else {
    console.warn(`Auth state not found for ${personaKey}, using fresh context`);
  }

  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();

  // Restore sessionStorage (not handled by storageState)
  await restoreSessionStorage(page, personaKey, targetBaseURL);

  return { context, page };
}

/**
 * Custom test fixtures
 */
export type TestFixtures = {
  persona: Persona | null;
  authSession: AuthSession;
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

  // Mutable auth session — holds the active page/context pair.
  // Auth steps call authSession.switchPersona() to swap to a different persona.
  authSession: async ({ browser, page, context }, use) => {
    const extraContexts: BrowserContext[] = [];

    const session: AuthSession = {
      page,
      context,
      switchPersona: async (personaKey: PersonaKey, navigateUrl?: string) => {
        const { context: newCtx, page: newPage } = await createAuthenticatedContext(
          browser,
          personaKey,
          navigateUrl,
        );
        extraContexts.push(newCtx);
        session.page = newPage;
        session.context = newCtx;
      },
    };

    await use(session);

    // Cleanup extra contexts created during the test
    for (const ctx of extraContexts) {
      await ctx.close().catch(() => {});
    }
  },

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
 * Helper to load authenticated context for a specific persona.
 * Uses Playwright's storageState for proper session restoration.
 */
export async function loadPersonaContext(
  browser: Browser,
  personaKey: PersonaKey,
  baseURL?: string,
): Promise<BrowserContext> {
  const persona = PERSONAS[personaKey];
  const authStatePath = getAuthStatePath(personaKey);

  const options: Parameters<Browser['newContext']>[0] = {
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
