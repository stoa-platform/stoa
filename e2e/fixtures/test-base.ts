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
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// URLs
const PORTAL_URL = process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev';
const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'https://mcp.gostoa.dev';

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
    return stateData.sessionStorage && typeof stateData.sessionStorage === 'object'
      ? stateData.sessionStorage
      : {};
  } catch (error) {
    console.warn(`Failed to read auth state from ${resolvedPath}: ${String(error)}`);
    return {};
  }
}

/**
 * Parse an OIDC storage key of the form `oidc.user:{authority}:{clientId}`
 * and extract authority + clientId. Returns null on malformed keys.
 */
function parseOidcStorageKey(key: string): { authority: string; clientId: string } | null {
  const prefix = 'oidc.user:';
  if (!key.startsWith(prefix)) return null;
  const rest = key.slice(prefix.length);
  const colonBeforeClient = rest.lastIndexOf(':');
  if (colonBeforeClient < 0) return null;
  return {
    authority: rest.slice(0, colonBeforeClient),
    clientId: rest.slice(colonBeforeClient + 1),
  };
}

/**
 * Refresh any expired OIDC access tokens in sessionData by POSTing a
 * `refresh_token` grant to the authority's token endpoint. Returns a new
 * sessionData map with refreshed blobs (and original blobs left untouched
 * when the token is still valid or the refresh fails).
 *
 * Root cause this addresses: KC default access_token lifespan is ~5min, but
 * E2E jobs take 4-9min between auth-setup and the failing test. React-OIDC's
 * silent renew relies on an iframe that needs SameSite=None KC cookies — and
 * those aren't preserved across Playwright contexts. Refreshing directly via
 * refresh_token grant bypasses the iframe path entirely.
 */
async function refreshExpiredOidcTokens(
  sessionData: Record<string, string>,
): Promise<Record<string, string>> {
  const now = Math.floor(Date.now() / 1000);
  const EXPIRY_BUFFER_S = 60; // refresh if token expires within 60s
  const refreshed: Record<string, string> = { ...sessionData };

  for (const [key, rawValue] of Object.entries(sessionData)) {
    const parsed = parseOidcStorageKey(key);
    if (!parsed) continue;

    let blob: Record<string, unknown>;
    try {
      blob = JSON.parse(rawValue);
    } catch {
      continue;
    }
    const expiresAt = typeof blob.expires_at === 'number' ? blob.expires_at : 0;
    const refreshToken = typeof blob.refresh_token === 'string' ? blob.refresh_token : '';
    if (!refreshToken) continue;
    if (expiresAt > now + EXPIRY_BUFFER_S) continue; // still valid

    try {
      const tokenUrl = `${parsed.authority}/protocol/openid-connect/token`;
      const response = await fetch(tokenUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: parsed.clientId,
          grant_type: 'refresh_token',
          refresh_token: refreshToken,
        }),
      });
      if (!response.ok) {
        console.warn(
          `[auth-harness] refresh failed for ${parsed.clientId}: HTTP ${response.status}`,
        );
        continue;
      }
      const tokens = (await response.json()) as {
        access_token: string;
        refresh_token?: string;
        id_token?: string;
        expires_in: number;
        scope?: string;
        token_type?: string;
      };
      const nextBlob = {
        ...blob,
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token ?? refreshToken,
        id_token: tokens.id_token ?? blob.id_token,
        token_type: tokens.token_type ?? blob.token_type ?? 'Bearer',
        scope: tokens.scope ?? blob.scope,
        expires_at: Math.floor(Date.now() / 1000) + tokens.expires_in,
      };
      // Update profile if id_token was rotated (claims may have changed)
      if (tokens.id_token) {
        try {
          const payload = tokens.id_token.split('.')[1];
          nextBlob.profile = JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8'));
        } catch {
          // Keep existing profile
        }
      }
      refreshed[key] = JSON.stringify(nextBlob);
      console.log(
        `[auth-harness] refreshed ${parsed.clientId} token (was exp=${expiresAt}, now exp=${nextBlob.expires_at})`,
      );
    } catch (error) {
      console.warn(
        `[auth-harness] refresh threw for ${parsed.clientId}: ${String(error)}`,
      );
    }
  }

  return refreshed;
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
 * Ensure the captured OIDC user is present in the page's sessionStorage after navigation.
 * Defensive guard against the addInitScript / React-OIDC boot race that surfaced in
 * run 24750762663 as "Login with Keycloak" on otherwise-authenticated Console tests.
 *
 * If the OIDC entry is missing, re-inject sessionStorage via page.evaluate and reload
 * once. If still missing after reload, throw — the caller needs the auth gate cleared.
 */
async function ensureSessionStorageLoaded(
  page: Page,
  sessionData: Record<string, string>,
): Promise<void> {
  if (Object.keys(sessionData).length === 0) return;

  const oidcKeys = Object.keys(sessionData).filter((k) => k.startsWith('oidc.user:'));
  if (oidcKeys.length === 0) return;

  const hasAnyOidcEntry = await page
    .evaluate((keys: string[]) => keys.some((k) => sessionStorage.getItem(k) !== null), oidcKeys)
    .catch(() => false);

  if (hasAnyOidcEntry) return;

  // Race fallback: reinject from the captured JSON blob and reload once.
  await page
    .evaluate((data: Record<string, string>) => {
      for (const [k, v] of Object.entries(data)) {
        try {
          sessionStorage.setItem(k, v);
        } catch {
          // Ignore origins where sessionStorage is unavailable.
        }
      }
    }, sessionData)
    .catch(() => undefined);
  await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => undefined);

  const hasAfterReload = await page
    .evaluate((keys: string[]) => keys.some((k) => sessionStorage.getItem(k) !== null), oidcKeys)
    .catch(() => false);
  if (!hasAfterReload) {
    throw new Error(
      '[auth-harness] OIDC sessionStorage not loaded after reinject + reload. ' +
        'Persona auth state is missing or the browser blocked the write.',
    );
  }
}

async function createContextFromStorageState(
  browser: Browser,
  storageStatePath?: string,
  baseURL?: string,
): Promise<{ context: BrowserContext; page: Page; sessionData: Record<string, string> }> {
  const resolvedStorageStatePath = storageStatePath
    ? resolveAuthStatePath(storageStatePath)
    : undefined;
  const contextOptions: Parameters<Browser['newContext']>[0] = { baseURL };

  if (resolvedStorageStatePath && fs.existsSync(resolvedStorageStatePath)) {
    contextOptions.storageState = resolvedStorageStatePath;
  } else if (resolvedStorageStatePath) {
    console.warn(`Auth state not found at ${resolvedStorageStatePath}, using fresh context`);
  }

  const context = await browser.newContext(contextOptions);
  let sessionData: Record<string, string> = {};
  if (resolvedStorageStatePath) {
    sessionData = await refreshExpiredOidcTokens(
      loadSessionStorageFromAuthState(resolvedStorageStatePath),
    );
    await installSessionStorageInitScript(context, sessionData);
  }

  const page = await context.newPage();
  return { context, page, sessionData };
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
): Promise<{ context: BrowserContext; page: Page; sessionData: Record<string, string> }> {
  const persona = PERSONAS[personaKey];
  const targetBaseURL =
    baseURL || (persona.defaultApp === 'portal' ? PORTAL_URL : CONSOLE_URL);
  return createContextFromStorageState(browser, getAuthStatePath(personaKey), targetBaseURL);
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
  authSession: async ({ browser }, use, testInfo) => {
    const projectStorageState =
      typeof testInfo.project.use.storageState === 'string'
        ? testInfo.project.use.storageState
        : undefined;
    const projectBaseURL =
      typeof testInfo.project.use.baseURL === 'string'
        ? testInfo.project.use.baseURL
        : undefined;
    const initialSession = await createContextFromStorageState(
      browser,
      projectStorageState,
      projectBaseURL,
    );
    const contextsToClose = new Set<BrowserContext>([initialSession.context]);

    const session: AuthSession = {
      page: initialSession.page,
      context: initialSession.context,
      switchPersona: async (personaKey: PersonaKey, navigateUrl?: string) => {
        const nextSession = await createAuthenticatedContext(
          browser,
          personaKey,
          navigateUrl || projectBaseURL,
        );
        contextsToClose.add(nextSession.context);
        session.page = nextSession.page;
        session.context = nextSession.context;

        // Pre-navigate + verify OIDC sessionStorage loaded with freshly refreshed
        // tokens — closes both the addInitScript/React-OIDC boot race AND the
        // token-expiry window (KC default 5min access_token TTL vs 4-9min CI runs).
        if (navigateUrl) {
          await nextSession.page.goto(navigateUrl, { waitUntil: 'domcontentloaded' });
          await ensureSessionStorageLoaded(nextSession.page, nextSession.sessionData);
        }
      },
    };

    await use(session);

    for (const ctx of contextsToClose) {
      await ctx.close().catch(() => {});
    }
  },

  // The default page fixture must follow authSession.switchPersona().
  page: async ({ authSession }, use) => {
    const proxy = new Proxy(
      {},
      {
        get(_target, prop) {
          const currentPage = authSession.page as unknown as Record<PropertyKey, unknown>;
          const value = currentPage[prop];
          return typeof value === 'function' ? value.bind(authSession.page) : value;
        },
        set(_target, prop, value) {
          (authSession.page as unknown as Record<PropertyKey, unknown>)[prop] = value;
          return true;
        },
        has(_target, prop) {
          return prop in (authSession.page as unknown as Record<PropertyKey, unknown>);
        },
      },
    ) as Page;

    await use(proxy);
  },

  context: async ({ authSession }, use) => {
    const proxy = new Proxy(
      {},
      {
        get(_target, prop) {
          const currentContext = authSession.context as unknown as Record<PropertyKey, unknown>;
          const value = currentContext[prop];
          return typeof value === 'function' ? value.bind(authSession.context) : value;
        },
        set(_target, prop, value) {
          (authSession.context as unknown as Record<PropertyKey, unknown>)[prop] = value;
          return true;
        },
        has(_target, prop) {
          return prop in (authSession.context as unknown as Record<PropertyKey, unknown>);
        },
      },
    ) as BrowserContext;

    await use(proxy);
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
      await refreshExpiredOidcTokens(loadSessionStorageFromAuthState(authStatePath)),
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
    await refreshExpiredOidcTokens(loadSessionStorageFromAuthState(authStatePath)),
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
