/**
 * Authentication Setup for STOA E2E Tests
 * Authenticates all personas via Keycloak and saves storage states.
 *
 * Note: react-oidc-context stores OIDC tokens in sessionStorage (not localStorage).
 * Playwright's storageState() only captures cookies + localStorage, so we explicitly
 * capture sessionStorage and merge it into the state file for test restoration.
 */

import { test as setup, expect } from '@playwright/test';
import { PERSONAS, PersonaKey, getAuthStatePath } from './personas';
import * as fs from 'fs';

const PORTAL_URL = process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev';

/**
 * Setup authentication for each persona
 */
for (const [personaKey, persona] of Object.entries(PERSONAS) as [PersonaKey, typeof PERSONAS[PersonaKey]][]) {
  setup(`authenticate ${persona.name} (${personaKey})`, async ({ page }) => {
    // Skip if no password configured
    if (!persona.password) {
      console.warn(`Skipping auth for ${personaKey}: no password configured`);
      return;
    }

    // Determine target URL based on persona's default app
    const targetUrl = persona.defaultApp === 'portal' ? PORTAL_URL : CONSOLE_URL;

    console.log(`Authenticating ${persona.name} at ${targetUrl}...`);

    // Navigate to the application
    await page.goto(targetUrl);

    // Wait for either Keycloak login form or app's login button
    await page.waitForSelector('#username, button:has-text("Sign in"), button:has-text("Login"), button:has-text("Se connecter")', {
      timeout: 30000,
    });

    // Check if we need to click a login button first
    const loginButton = page.locator('button:has-text("Sign in"), button:has-text("Login"), button:has-text("Se connecter")');
    if (await loginButton.isVisible()) {
      await loginButton.first().click();
      // Wait for Keycloak redirect
      await page.waitForSelector('#username', { timeout: 30000 });
    }

    // Fill Keycloak login form
    await page.locator('#username').fill(persona.username);
    await page.locator('#password').fill(persona.password);

    // Submit login
    await page.locator('#kc-login').click();

    // Wait for redirect back to application
    await page.waitForURL(
      url => !url.hostname.includes('auth.') && !url.pathname.includes('/auth/'),
      { timeout: 30000 }
    );

    // Wait for OIDC callback to complete — tokens stored in sessionStorage
    await page.waitForFunction(
      () => {
        const keys = Object.keys(sessionStorage);
        return keys.some(k => k.startsWith('oidc.'));
      },
      { timeout: 15000 },
    ).catch(() => {
      console.warn(`${personaKey}: OIDC session keys not found in sessionStorage`);
    });

    // Wait for app to fully load (no loading spinner)
    await expect(page.locator('text=Loading..., .animate-spin').first()).not.toBeVisible({ timeout: 15000 }).catch(() => {
      // Loading indicator might not exist, that's ok
    });

    // Verify we're authenticated
    const currentUrl = page.url();
    expect(currentUrl).not.toContain('/login');
    expect(currentUrl).not.toContain('/auth/');

    console.log(`${persona.name} authenticated successfully`);

    // Save Playwright storage state (cookies + localStorage)
    const authStatePath = getAuthStatePath(personaKey);
    await page.context().storageState({ path: authStatePath });

    // Capture sessionStorage (contains OIDC tokens from react-oidc-context)
    const sessionStorageData: Record<string, string> = await page.evaluate(() => {
      const data: Record<string, string> = {};
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key) {
          data[key] = sessionStorage.getItem(key) || '';
        }
      }
      return data;
    });

    // Merge sessionStorage into the state file
    const stateFile = JSON.parse(fs.readFileSync(authStatePath, 'utf-8'));
    stateFile.sessionStorage = sessionStorageData;
    fs.writeFileSync(authStatePath, JSON.stringify(stateFile, null, 2));

    const oidcKeys = Object.keys(sessionStorageData).filter(k => k.startsWith('oidc.'));
    console.log(`Storage state saved to ${authStatePath} (${oidcKeys.length} OIDC keys captured)`);
  });
}
