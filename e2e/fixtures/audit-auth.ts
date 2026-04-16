/**
 * Shared login helper for audit tests (CAB-1970).
 * Uses Keycloak DOM IDs (#username, #password, #kc-login) — proven pattern from local-deploy.spec.ts.
 */
import type { Page } from '@playwright/test';

const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'http://localhost:3000';
const PARZIVAL_USER = process.env.PARZIVAL_USER || 'parzival';
const PARZIVAL_PASSWORD = (() => {
  const v = process.env.PARZIVAL_PASSWORD;
  if (!v) throw new Error('PARZIVAL_PASSWORD env var is required');
  return v;
})();

export async function loginAndGetToken(page: Page): Promise<string> {
  await page.goto(CONSOLE_URL);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);

  // Already authenticated (SSO session)?
  const loggedIn = await page
    .locator('text=Hello,')
    .isVisible({ timeout: 3000 })
    .catch(() => false);

  if (!loggedIn) {
    // Step 1: Click "Login with Keycloak"
    const loginBtn = page.getByRole('button', { name: 'Login with Keycloak' });
    await loginBtn.waitFor({ state: 'visible', timeout: 10_000 });
    await loginBtn.click();

    // Step 2: Fill KC form (Keycloak DOM IDs)
    await page.locator('#username').waitFor({ state: 'visible', timeout: 15_000 });
    await page.locator('#username').fill(PARZIVAL_USER);
    await page.locator('#password').fill(PARZIVAL_PASSWORD);

    // Step 3: Submit and wait for redirect back
    await page.locator('#kc-login').click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
  }

  // Extract token from oidc-client-ts localStorage
  return page.evaluate(() => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith('oidc.user:')) {
        return JSON.parse(localStorage.getItem(key) || '{}').access_token || '';
      }
    }
    return '';
  });
}
