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
import * as path from 'path';

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
 * Resolve auth state paths relative to the e2e workspace root.
 */
function resolveAuthStatePath(authStatePath: string): string {
  return path.isAbsolute(authStatePath)
    ? authStatePath
    : path.resolve(__dirname, '..', authStatePath);
}

/**
 * Load custom sessionStorage persisted alongside Playwright's storageState.
 * Playwright restores only cookies + localStorage natively; our auth setup writes
 * OIDC sessionStorage into the same JSON file under a custom `sessionStorage` key.
 */
function loadSessionStorageFromAuthState(authStatePath: string): Record<string, string> {
  const resolvedPath = resolveAuthStatePath(authStatePath);
  if (!fs.existsSync(resolvedPath)) return {};

  try {
    const stateData = JSON.parse(fs.readFileSync(resolvedPath, 'utf-8'));
    if (!stateData.sessionStorage || typeof stateData.sessionStorage !== 'object') {
      return {};
    }
    return stateData.sessionStorage;
  } catch (error) {
    console.warn(`Failed to read auth state from ${resolvedPath}: ${String(error)}`);
    return {};
  }
}

/**
 * Inject persisted sessionStorage into every page created in the context.
 * The init script runs before app code on each navigation, which keeps `{ page }`
 * fixtures aligned with `authSession.page`.
 */
async function installSessionStorageInitScript(
  context: BrowserContext,
  sessionData: Record<string, string>,
): Promise<void> {
  if (Object.keys(sessionData).length === 0) return;

  await context.addInitScript((data: Record<string, string>) => {
    for (const [key, value] of Object.entries(data)) {
      try {
        sessionStorage.setItem(key, value);
      } catch {
        // Ignore pages/origins where sessionStorage is unavailable.
      }
    }
  }, sessionData);
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
  const authStatePath = resolveAuthStatePath(getAuthStatePath(personaKey));
  const targetBaseURL =
    baseURL || (persona.defaultApp === 'portal' ? PORTAL_URL : CONSOLE_URL);

  const contextOptions: Parameters<Browser['newContext']>[0] = { baseURL: targetBaseURL };

  if (fs.existsSync(authStatePath)) {
    contextOptions.storageState = authStatePath;
  } else {
    console.warn(`Auth state not found for ${personaKey}, using fresh context`);
  }

  const context = await browser.newContext(contextOptions);
  await installSessionStorageInitScript(
    context,
    loadSessionStorageFromAuthState(authStatePath),
  );
  const page = await context.newPage();

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
  // Keep the default Playwright page/context fixtures, but add our custom
  // sessionStorage restoration before any test page is created.
  context: async ({ context }, use, testInfo) => {
    const projectStorageState = testInfo.project.use.storageState;
    if (typeof projectStorageState === 'string') {
      await installSessionStorageInitScript(
        context,
        loadSessionStorageFromAuthState(projectStorageState),
      );
    }

    await use(context);
  },

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
    const authStatePath = resolveAuthStatePath(getAuthStatePath(personaKey));

    let context;
    if (fs.existsSync(authStatePath)) {
      context = await browser.newContext({
        storageState: authStatePath,
      });
    } else {
      console.warn(`Auth state not found for ${personaKey}, using fresh context`);
      context = await browser.newContext();
    }

    await installSessionStorageInitScript(
      context,
      loadSessionStorageFromAuthState(authStatePath),
    );

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
  const authStatePath = resolveAuthStatePath(getAuthStatePath(personaKey));

  const options: Parameters<Browser['newContext']>[0] = {
    baseURL: baseURL || (persona.defaultApp === 'portal' ? PORTAL_URL : CONSOLE_URL),
  };

  if (fs.existsSync(authStatePath)) {
    options.storageState = authStatePath;
  } else {
    console.warn(`Auth state not found for ${personaKey}`);
  }

  const context = await browser.newContext(options);
  await installSessionStorageInitScript(
    context,
    loadSessionStorageFromAuthState(authStatePath),
  );
  return context;
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
