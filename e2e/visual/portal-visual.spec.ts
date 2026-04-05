import { test, expect } from '@playwright/test';
import { buildMaskLocators } from './mask-helper';

/**
 * Portal Visual Regression — 3 key pages (CAB-1994)
 *
 * Golden baselines in e2e/golden/portal-visual/.
 * Uses Portal mock routes for API interception.
 *
 * Note: Portal mock routes are injected inline since the Portal
 * uses a different OIDC client than Console.
 */

const MOCK_USER_INFO = {
  sub: 'user-1',
  email: 'parzival@high-five.io',
  name: 'Parzival',
  preferred_username: 'parzival',
  realm_access: { roles: ['tenant-admin'] },
  resource_access: { 'stoa-portal': { roles: ['tenant-admin'] } },
};

async function setupPortalMocks(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/auth/realms/stoa/.well-known/openid-configuration', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        issuer: 'http://localhost:4174/auth/realms/stoa',
        authorization_endpoint: 'http://localhost:4174/auth/realms/stoa/protocol/openid-connect/auth',
        token_endpoint: 'http://localhost:4174/auth/realms/stoa/protocol/openid-connect/token',
        userinfo_endpoint: 'http://localhost:4174/auth/realms/stoa/protocol/openid-connect/userinfo',
        jwks_uri: 'http://localhost:4174/auth/realms/stoa/protocol/openid-connect/certs',
        end_session_endpoint: 'http://localhost:4174/auth/realms/stoa/protocol/openid-connect/logout',
      }),
    }),
  );

  await page.route('**/auth/realms/stoa/protocol/openid-connect/userinfo', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER_INFO) }),
  );

  await page.route('**/auth/realms/stoa/protocol/openid-connect/certs', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ keys: [] }) }),
  );

  await page.route('**/api/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  await page.route('**/api/health', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
  );
}

async function injectPortalAuth(page: import('@playwright/test').Page): Promise<void> {
  const mockToken = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEiLCJlbWFpbCI6InBhcnppdmFsQGhpZ2gtZml2ZS5pbyIsIm5hbWUiOiJQYXJ6aXZhbCIsInByZWZlcnJlZF91c2VybmFtZSI6InBhcnppdmFsIiwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbInRlbmFudC1hZG1pbiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7InN0b2EtcG9ydGFsIjp7InJvbGVzIjpbInRlbmFudC1hZG1pbiJdfX0sImV4cCI6OTk5OTk5OTk5OSwiaWF0IjoxNzAwMDAwMDAwLCJpc3MiOiJodHRwOi8vbG9jYWxob3N0OjQxNzQvYXV0aC9yZWFsbXMvc3RvYSJ9.mock-signature';

  const oidcKey = `oidc.user:http://localhost:4174/auth/realms/stoa:stoa-portal`;
  const oidcData = JSON.stringify({
    access_token: mockToken,
    token_type: 'Bearer',
    scope: 'openid profile email',
    profile: MOCK_USER_INFO,
    expires_at: 9999999999,
  });

  await page.addInitScript(
    (data: { key: string; value: string }) => {
      sessionStorage.setItem(data.key, data.value);
    },
    { key: oidcKey, value: oidcData },
  );
}

test.beforeEach(async ({ page }) => {
  await setupPortalMocks(page);
  await injectPortalAuth(page);
});

test('Home visual baseline', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const mask = buildMaskLocators(page);
  await expect(page).toHaveScreenshot('home.png', { mask, fullPage: true });
});

test('API Catalog visual baseline', async ({ page }) => {
  await page.goto('/apis');
  await page.waitForLoadState('networkidle');
  const mask = buildMaskLocators(page);
  await expect(page).toHaveScreenshot('api-catalog.png', { mask, fullPage: true });
});

test('Subscriptions visual baseline', async ({ page }) => {
  await page.goto('/subscriptions');
  await page.waitForLoadState('networkidle');
  const mask = buildMaskLocators(page);
  await expect(page).toHaveScreenshot('subscriptions.png', { mask, fullPage: true });
});
