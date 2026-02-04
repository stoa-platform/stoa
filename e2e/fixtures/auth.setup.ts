/**
 * Authentication Setup for STOA E2E Tests
 * Authenticates all personas via Keycloak and saves storage states.
 *
 * Note: react-oidc-context stores OIDC tokens in sessionStorage (not localStorage).
 * Playwright's storageState() only captures cookies + localStorage, so we explicitly
 * capture sessionStorage and merge it into the state file for test restoration.
 *
 * Each persona authenticates on BOTH portal and console (different OIDC clients:
 * stoa-portal vs control-plane-ui). The merged sessionStorage contains tokens for
 * both clients, so restoreAuthState works regardless of which app is being tested.
 */

import { test as setup, expect } from '@playwright/test';
import { PERSONAS, PersonaKey, getAuthStatePath } from './personas';
import * as fs from 'fs';

const PORTAL_URL = process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev';

/**
 * Perform Keycloak login flow (click SSO button if needed, fill form, wait for redirect)
 */
async function keycloakLogin(
  page: import('@playwright/test').Page,
  username: string,
  password: string,
  targetUrl: string,
): Promise<void> {
  await page.goto(targetUrl);

  // Wait for either Keycloak login form or app's login button
  await page.waitForSelector(
    '#username, button:has-text("Sign in"), button:has-text("Login"), button:has-text("Se connecter"), a:has-text("Sign in")',
    { timeout: 30000 },
  );

  // Check if we need to click a login button first (portal/console login page)
  const loginButton = page.locator(
    'button:has-text("Sign in"), button:has-text("Login"), button:has-text("Se connecter"), a:has-text("Sign in")',
  );
  if (await loginButton.isVisible()) {
    await loginButton.first().click();
  }

  // Wait for Keycloak login form (may auto-SSO if cookies are valid)
  const isOnKeycloak = await page
    .waitForSelector('#username', { timeout: 5000 })
    .then(() => true)
    .catch(() => false);

  if (isOnKeycloak) {
    await page.locator('#username').fill(username);
    await page.locator('#password').fill(password);
    await page.locator('#kc-login').click();
  }

  // Wait for redirect back to application
  await page.waitForURL(
    url => !url.hostname.includes('auth.') && !url.pathname.includes('/auth/'),
    { timeout: 30000 },
  );

  // Wait for OIDC callback — tokens stored in sessionStorage
  await page
    .waitForFunction(
      () => Object.keys(sessionStorage).some(k => k.startsWith('oidc.')),
      { timeout: 15000 },
    )
    .catch(() => {});

  // Wait for app to fully load
  await expect(
    page.locator('text=Loading..., .animate-spin').first(),
  )
    .not.toBeVisible({ timeout: 10000 })
    .catch(() => {});
}

/**
 * Capture sessionStorage from the current page
 */
async function captureSessionStorage(
  page: import('@playwright/test').Page,
): Promise<Record<string, string>> {
  return page.evaluate(() => {
    const data: Record<string, string> = {};
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key) {
        data[key] = sessionStorage.getItem(key) || '';
      }
    }
    return data;
  });
}

/**
 * Setup authentication for each persona on both portal and console
 */
for (const [personaKey, persona] of Object.entries(PERSONAS) as [PersonaKey, typeof PERSONAS[PersonaKey]][]) {
  setup(`authenticate ${persona.name} (${personaKey})`, async ({ page }) => {
    if (!persona.password) {
      console.warn(`Skipping auth for ${personaKey}: no password configured`);
      return;
    }

    const defaultUrl = persona.defaultApp === 'portal' ? PORTAL_URL : CONSOLE_URL;
    const otherUrl = persona.defaultApp === 'portal' ? CONSOLE_URL : PORTAL_URL;

    // ── Step 1: Authenticate on default app (full Keycloak login) ────────
    console.log(`Authenticating ${persona.name} at ${defaultUrl}...`);
    await keycloakLogin(page, persona.username, persona.password, defaultUrl);

    const currentUrl = page.url();
    expect(currentUrl).not.toContain('/login');
    expect(currentUrl).not.toContain('/auth/');
    console.log(`${persona.name} authenticated successfully`);

    // Capture default app sessionStorage
    const defaultSessionStorage = await captureSessionStorage(page);

    // ── Step 2: SSO to the other app (Keycloak cookies auto-login) ──────
    console.log(`SSO ${persona.name} to ${otherUrl}...`);
    await keycloakLogin(page, persona.username, persona.password, otherUrl);

    // Capture other app sessionStorage
    const otherSessionStorage = await captureSessionStorage(page);

    // ── Step 3: Save merged state ───────────────────────────────────────
    const authStatePath = getAuthStatePath(personaKey);
    await page.context().storageState({ path: authStatePath });

    // Merge sessionStorage from both apps (different OIDC client keys coexist)
    const mergedSessionStorage = {
      ...defaultSessionStorage,
      ...otherSessionStorage,
    };

    const stateFile = JSON.parse(fs.readFileSync(authStatePath, 'utf-8'));
    stateFile.sessionStorage = mergedSessionStorage;
    fs.writeFileSync(authStatePath, JSON.stringify(stateFile, null, 2));

    const oidcKeys = Object.keys(mergedSessionStorage).filter(k => k.startsWith('oidc.'));
    console.log(
      `Storage state saved to ${authStatePath} (${oidcKeys.length} OIDC keys: ${oidcKeys.join(', ')})`,
    );
  });
}
