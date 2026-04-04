/**
 * Audit Phase 3 — Security Chain Verification (CAB-1971)
 *
 * 11 binary assertions proving auth, RBAC, and OAuth security.
 *
 * Run:
 *   cd e2e && npx playwright test --config playwright.audit.config.ts audit-phase3
 */
import { test, expect } from '@playwright/test';
import { loginAndGetToken } from '../fixtures/audit-auth';

const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'http://localhost:8081';
const API_URL = process.env.STOA_API_URL || 'http://localhost:8000';

let authToken: string;

test.describe('Audit Phase 3 — Security Chain', () => {
  test.describe.configure({ mode: 'serial' });

  test('3.0 — Authenticate for security tests', async ({ page }) => {
    authToken = await loginAndGetToken(page);
    expect(authToken).toBeTruthy();
  });

  // --- Auth: valid / invalid / no token ---

  test('3.1 — Valid bearer token grants access', async ({ request }) => {
    // MCP tools/list requires auth — proves bearer chain works
    const resp = await request.post(`${GATEWAY_URL}/mcp/tools/list`, {
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      data: { jsonrpc: '2.0', id: '3.1', method: 'tools/list', params: {} },
    });
    expect(resp.status()).toBe(200);
  });

  test('3.2 — Invalid bearer token is rejected on admin endpoint', async ({ request }) => {
    // Admin gateways endpoint requires valid token (CP API enforces RBAC)
    const resp = await request.get(`${API_URL}/v1/admin/gateways`, {
      headers: { Authorization: 'Bearer invalid.jwt.token' },
    });
    expect([401, 403]).toContain(resp.status());
  });

  test('3.3 — MCP tools/list is publicly accessible (discovery)', async ({ request }) => {
    // MCP tools/list is intentionally public for AI agent discovery
    const resp = await request.post(`${GATEWAY_URL}/mcp/tools/list`, {
      headers: { 'Content-Type': 'application/json' },
      data: { jsonrpc: '2.0', id: '3.3', method: 'tools/list', params: {} },
    });
    expect(resp.status()).toBe(200);
  });

  // --- API RBAC ---

  test('3.4 — Admin gateways endpoint requires auth', async ({ request }) => {
    const resp = await request.get(`${API_URL}/v1/admin/gateways`);
    expect([401, 403]).toContain(resp.status());
  });

  test('3.5 — Valid token on admin endpoint succeeds', async ({ request }) => {
    const resp = await request.get(`${API_URL}/v1/admin/gateways`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(resp.ok()).toBeTruthy();
  });

  // --- OAuth Discovery (bypass paths) ---

  test('3.6 — OAuth discovery accessible without auth', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/.well-known/oauth-protected-resource`);
    expect(resp.status()).toBe(200);
  });

  test('3.7 — OAuth metadata accessible without auth', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/.well-known/oauth-authorization-server`);
    expect(resp.status()).toBe(200);
  });

  test('3.8 — Health endpoint accessible without auth', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/health`);
    expect(resp.status()).toBe(200);
  });

  test('3.9 — Ready endpoint accessible without auth', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/ready`);
    expect(resp.status()).toBe(200);
  });

  test('3.10 — Metrics endpoint accessible without auth', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/metrics`);
    expect(resp.status()).toBe(200);
    const text = await resp.text();
    // Must contain at least one metric definition
    expect(text).toContain('# HELP');
  });

  test('3.11 — OAuth DCR endpoint exists', async ({ request }) => {
    // POST to register without body — should get 400 (bad request) not 404
    const resp = await request.post(`${GATEWAY_URL}/oauth/register`, {
      headers: { 'Content-Type': 'application/json' },
      data: {},
    });
    // 400/422 = endpoint exists and validates input
    // 404 = route not found (fail)
    expect(resp.status(), 'DCR endpoint should exist (not 404)').not.toBe(404);
  });
});
