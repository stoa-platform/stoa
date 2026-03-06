import { Page } from '@playwright/test';

/**
 * Mock API responses for smoke tests.
 * Intercepts all API calls and returns minimal valid responses
 * so the Console app renders without a live backend.
 */

const MOCK_TENANT = {
  id: 'tenant-1',
  name: 'high-five',
  display_name: 'High Five',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
};

const MOCK_USER_INFO = {
  sub: 'user-1',
  email: 'parzival@high-five.io',
  name: 'Parzival',
  preferred_username: 'parzival',
  realm_access: { roles: ['tenant-admin'] },
  resource_access: { 'control-plane-ui': { roles: ['tenant-admin'] } },
};

export async function setupMockRoutes(page: Page): Promise<void> {
  // Mock Keycloak OIDC discovery
  await page.route('**/auth/realms/stoa/.well-known/openid-configuration', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        issuer: 'http://localhost:4173/auth/realms/stoa',
        authorization_endpoint: 'http://localhost:4173/auth/realms/stoa/protocol/openid-connect/auth',
        token_endpoint: 'http://localhost:4173/auth/realms/stoa/protocol/openid-connect/token',
        userinfo_endpoint: 'http://localhost:4173/auth/realms/stoa/protocol/openid-connect/userinfo',
        jwks_uri: 'http://localhost:4173/auth/realms/stoa/protocol/openid-connect/certs',
        end_session_endpoint: 'http://localhost:4173/auth/realms/stoa/protocol/openid-connect/logout',
      }),
    }),
  );

  // Mock Keycloak userinfo
  await page.route('**/auth/realms/stoa/protocol/openid-connect/userinfo', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER_INFO) }),
  );

  // Mock Keycloak certs (empty — we don't validate tokens in mock mode)
  await page.route('**/auth/realms/stoa/protocol/openid-connect/certs', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ keys: [] }) }),
  );

  // Mock API health
  await page.route('**/api/health', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
  );

  // Mock tenants
  await page.route('**/api/v1/tenants**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [MOCK_TENANT], total: 1 }),
    }),
  );

  // Mock APIs catalog
  await page.route('**/api/v1/apis**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock subscriptions
  await page.route('**/api/v1/subscriptions**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock deployments
  await page.route('**/api/v1/deployments**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock gateway instances
  await page.route('**/api/v1/gateway-instances**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock applications
  await page.route('**/api/v1/applications**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock AI tools
  await page.route('**/api/v1/ai-tools**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock MCP servers
  await page.route('**/api/v1/mcp-servers**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock consumers
  await page.route('**/api/v1/consumers**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock metrics/analytics
  await page.route('**/api/v1/metrics**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) }),
  );

  // Mock analytics
  await page.route('**/api/v1/analytics**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) }),
  );

  // Mock policies
  await page.route('**/api/v1/policies**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Mock error snapshots
  await page.route('**/api/v1/error-snapshots**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }),
  );

  // Catch-all for other API routes — return empty success
  await page.route('**/api/v1/**', (route) => {
    if (!route.request().url().includes('already-handled')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      });
    }
    return route.continue();
  });
}

/**
 * Inject mock OIDC auth state into the page's sessionStorage.
 * This simulates a logged-in user without needing Keycloak.
 */
export async function injectMockAuth(page: Page): Promise<void> {
  const mockToken = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEiLCJlbWFpbCI6InBhcnppdmFsQGhpZ2gtZml2ZS5pbyIsIm5hbWUiOiJQYXJ6aXZhbCIsInByZWZlcnJlZF91c2VybmFtZSI6InBhcnppdmFsIiwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbInRlbmFudC1hZG1pbiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImNvbnRyb2wtcGxhbmUtdWkiOnsicm9sZXMiOlsidGVuYW50LWFkbWluIl19fSwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDAsImlzcyI6Imh0dHA6Ly9sb2NhbGhvc3Q6NDE3My9hdXRoL3JlYWxtcy9zdG9hIn0.mock-signature';

  const oidcKey = `oidc.user:http://localhost:4173/auth/realms/stoa:control-plane-ui`;
  const oidcData = JSON.stringify({
    access_token: mockToken,
    token_type: 'Bearer',
    scope: 'openid profile email',
    profile: MOCK_USER_INFO,
    expires_at: 9999999999,
  });

  await page.addInitScript((data: { key: string; value: string }) => {
    sessionStorage.setItem(data.key, data.value);
  }, { key: oidcKey, value: oidcData });
}
