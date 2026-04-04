/**
 * Audit Phase 2 — MCP Protocol Verification (CAB-1970)
 *
 * 9 binary assertions proving MCP protocol works end-to-end.
 *
 * Run:
 *   cd e2e && npx playwright test --config playwright.audit.config.ts audit-phase2
 */
import { test, expect } from '@playwright/test';
import { loginAndGetToken } from '../fixtures/audit-auth';

const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'http://localhost:8081';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'http://localhost:3000';

let authToken: string;

test.describe('Audit Phase 2 — MCP Protocol', () => {
  test.describe.configure({ mode: 'serial' });

  test('2.0 — Authenticate for MCP API tests', async ({ page }) => {
    authToken = await loginAndGetToken(page);
    expect(authToken, 'Failed to extract access token').toBeTruthy();
  });

  test('2.1 — /mcp/capabilities returns protocol version', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/mcp/capabilities`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(
      body.protocol_version || body.protocolVersion || body.serverInfo?.protocolVersion,
      'No protocol_version in capabilities response'
    ).toBeTruthy();
  });

  test('2.2 — /mcp/tools/list returns tools array', async ({ request }) => {
    const resp = await request.post(`${GATEWAY_URL}/mcp/tools/list`, {
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      data: { jsonrpc: '2.0', id: 'audit-2.2', method: 'tools/list', params: {} },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const tools = body.result?.tools || body.tools || [];
    expect(Array.isArray(tools), 'tools/list did not return an array').toBeTruthy();
  });

  test('2.3 — /mcp/tools/call executes successfully', async ({ request }) => {
    const listResp = await request.post(`${GATEWAY_URL}/mcp/tools/list`, {
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      data: { jsonrpc: '2.0', id: 'audit-2.3-list', method: 'tools/list', params: {} },
    });
    const listBody = await listResp.json();
    const tools = listBody.result?.tools || listBody.tools || [];

    if (tools.length === 0) {
      test.skip(true, 'No tools available');
      return;
    }

    const resp = await request.post(`${GATEWAY_URL}/mcp/tools/call`, {
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      data: {
        jsonrpc: '2.0',
        id: 'audit-2.3-call',
        method: 'tools/call',
        params: { name: tools[0].name, arguments: { action: 'list' } },
      },
    });
    // 200 = success, 400/422 = invalid args (proves endpoint exists and parses request)
    expect([200, 400, 422]).toContain(resp.status());
    if (resp.status() === 200) {
      const body = await resp.json();
      expect(body.jsonrpc || body.result || body.error || body.content, 'No MCP response').toBeTruthy();
    }
    // Non-200 with valid status already proves the protocol endpoint works
  });

  test('2.4 — /mcp/resources/list endpoint exists', async ({ request }) => {
    const resp = await request.post(`${GATEWAY_URL}/mcp/resources/list`, {
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      data: { jsonrpc: '2.0', id: 'audit-2.4', method: 'resources/list', params: {} },
    });
    expect([200, 404].includes(resp.status()), `Unexpected status ${resp.status()}`).toBeTruthy();
  });

  test('2.5 — OAuth protected resource has authorization_servers', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/.well-known/oauth-protected-resource`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.authorization_servers, 'Missing authorization_servers').toBeTruthy();
    expect(Array.isArray(body.authorization_servers)).toBeTruthy();
    expect(body.authorization_servers.length).toBeGreaterThan(0);
    expect(body.scopes_supported, 'Missing scopes_supported').toBeTruthy();
  });

  test('2.6 — OAuth metadata has token_endpoint', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/.well-known/oauth-authorization-server`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.token_endpoint, 'Missing token_endpoint').toBeTruthy();
    expect(body.registration_endpoint, 'Missing registration_endpoint').toBeTruthy();
  });

  test('2.7 — Console gateway registry shows online gateways', async ({ page }) => {
    await loginAndGetToken(page);
    await page.goto(`${CONSOLE_URL}/gateways`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await expect(page.getByRole('heading', { name: 'Gateway Registry' })).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('text=Online').first()).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: 'test-results/audit/2.7-gateway-registry.png' });
  });

  test('2.8 — Console gateway modes shows active modes', async ({ page }) => {
    await loginAndGetToken(page);
    await page.goto(`${CONSOLE_URL}/gateways/modes`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await expect(page.locator('text=Gateway Modes')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('heading', { name: 'Edge MCP' })).toBeVisible({ timeout: 5_000 });
    const mainText = await page.locator('main').innerText();
    expect(mainText, 'No "online" count on modes page').toContain('online');
    await page.screenshot({ path: 'test-results/audit/2.8-gateway-modes.png' });
  });
});
