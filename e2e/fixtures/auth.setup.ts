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
 * Diagnose what type of Keycloak page is currently shown.
 * Returns a description of the visible form elements for debugging.
 */
async function diagnoseKeycloakPage(
  page: import('@playwright/test').Page,
): Promise<string> {
  return page.evaluate(() => {
    const forms = Array.from(document.querySelectorAll('form')).map(f => f.id || f.action);
    const buttons = Array.from(
      document.querySelectorAll('button, input[type="submit"]'),
    ).map(b => `${b.tagName}[${b.getAttribute('name') || b.getAttribute('id') || b.textContent?.trim().slice(0, 30)}]`);
    const title = document.querySelector('#kc-page-title, .pf-c-title, h1')?.textContent?.trim();
    return `title="${title || 'none'}" forms=[${forms.join(',')}] buttons=[${buttons.join(',')}]`;
  });
}

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

  // Handle intermediate Keycloak pages (consent, terms, OTP, profile) before redirect.
  // After login, Keycloak may show additional forms (e.g. OAuth grant/consent
  // for the control-plane-ui client). We loop until we leave Keycloak.
  for (let attempt = 0; attempt < 5; attempt++) {
    const redirected = await page
      .waitForURL(
        url => !url.hostname.includes('auth.') && !url.pathname.includes('/auth/'),
        { timeout: 10000 },
      )
      .then(() => true)
      .catch(() => false);

    if (redirected) break;

    // Still on Keycloak — diagnose the page for debugging
    const currentUrl = page.url();
    const diagnosis = await diagnoseKeycloakPage(page).catch(() => 'evaluate failed');
    console.log(`  Keycloak intermediate page (attempt ${attempt + 1}/5): ${currentUrl}`);
    console.log(`  Page: ${diagnosis}`);

    // Case 1: OAuth consent/grant form — check for accept button specifically
    // Keycloak consent uses input[name="accept"] or button[name="accept"]
    const acceptButton = page.locator('input[name="accept"], button[name="accept"]');
    if (await acceptButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('  Found OAuth accept button — granting consent...');
      await acceptButton.click();
      continue;
    }

    // Case 2: Consent with Yes/Grant buttons (alternative Keycloak themes)
    const yesButton = page.locator(
      'button:has-text("Yes"), button:has-text("Grant access"), button:has-text("Accept")',
    );
    if (await yesButton.first().isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('  Found Yes/Grant button — clicking...');
      await yesButton.first().click();
      continue;
    }

    // Case 3: Consent with scope checkboxes — check all scopes then submit
    const scopeCheckboxes = page.locator(
      'input[type="checkbox"][name^="grant"], input[type="checkbox"].pf-c-check__input',
    );
    const checkboxCount = await scopeCheckboxes.count();
    if (checkboxCount > 0) {
      console.log(`  Found ${checkboxCount} scope checkboxes — checking all...`);
      for (let i = 0; i < checkboxCount; i++) {
        const cb = scopeCheckboxes.nth(i);
        if (!(await cb.isChecked())) await cb.check();
      }
      // After checking scopes, click the submit button
      const submitBtn = page.locator('#kc-login, input[type="submit"], button[type="submit"]');
      if (await submitBtn.first().isVisible({ timeout: 1000 }).catch(() => false)) {
        await submitBtn.first().click();
      }
      continue;
    }

    // Case 4: Update Password required action
    const newPasswordField = page.locator('#password-new');
    if (await newPasswordField.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('  Handling "Update Password" required action...');
      await newPasswordField.fill(password);
      await page.locator('#password-confirm').fill(password);
      await page.locator('#kc-login, input[type="submit"], button[type="submit"]').first().click();
      continue;
    }

    // Case 5: Update Profile required action
    const firstNameField = page.locator('#firstName');
    if (await firstNameField.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('  Handling "Update Profile" required action...');
      if ((await firstNameField.inputValue()) === '') await firstNameField.fill(username);
      const lastNameField = page.locator('#lastName');
      if (
        (await lastNameField.isVisible().catch(() => false)) &&
        (await lastNameField.inputValue()) === ''
      ) {
        await lastNameField.fill('Test');
      }
      const emailField = page.locator('#email');
      if (
        (await emailField.isVisible().catch(() => false)) &&
        (await emailField.inputValue()) === ''
      ) {
        await emailField.fill(`${username}@test.gostoa.dev`);
      }
      await page.locator('#kc-login, input[type="submit"], button[type="submit"]').first().click();
      continue;
    }

    // Case 6: Terms and Conditions — check the accept checkbox then submit
    const termsCheckbox = page.locator('#kc-accept, input[name="accept_terms"]');
    if (await termsCheckbox.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('  Handling Terms and Conditions...');
      if (!(await termsCheckbox.isChecked())) await termsCheckbox.check();
      await page.locator('#kc-login, input[type="submit"], button[type="submit"]').first().click();
      continue;
    }

    // Case 7: Generic #kc-login submit (last resort)
    const kcLogin = page.locator('#kc-login');
    if (await kcLogin.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log(`  Clicking #kc-login as last resort...`);
      await kcLogin.click();
      continue;
    }

    // Nothing recognizable — take screenshot for debugging and break
    console.warn(`  No recognizable form on Keycloak page: ${currentUrl}`);
    await page
      .screenshot({ path: `e2e/fixtures/.auth/debug-${username}-attempt-${attempt}.png` })
      .catch(() => {});
    break;
  }

  // Final wait for redirect (covers the case where consent/action was just approved)
  await page.waitForURL(
    url => !url.hostname.includes('auth.') && !url.pathname.includes('/auth/'),
    { timeout: 15000 },
  );

  // Wait for OIDC callback — tokens stored in sessionStorage
  // react-oidc-context may use 'oidc.' prefix or 'oidc.user:' prefix
  await page
    .waitForFunction(
      () => Object.keys(sessionStorage).some(k => k.startsWith('oidc.')),
      { timeout: 15000 },
    )
    .catch(() => {
      // Fallback: check for any auth-related key
      console.log(
        '  Warning: no oidc.* keys in sessionStorage after 15s',
      );
    });

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
