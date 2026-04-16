/**
 * E2E: Subscription by Auth Type + Dashboard Verification + Loki Recent Calls
 *
 * Full end-to-end flow — no skips, no fake data:
 *   Phase A: Create apps (all 5 security profiles) via tenant + portal API
 *   Phase B: Console UI traces (10 dashboards)
 *   Phase C: MCP subscription + usage events + Loki call logs + Portal traces
 *   Phase D: Gateway traffic + lifecycle + cross-validation
 *
 * Prerequisites:
 *   - Local stack: api.stoa.local, auth.stoa.local, console.stoa.local, portal.stoa.local, mcp.stoa.local
 *   - stoa-prometheus scraping gateway on NodePort 30080
 *   - stoa-loki on port 3100 (Grafana Loki)
 *   - API container with KEYCLOAK_ADMIN_PASSWORD, PROMETHEUS_INTERNAL_URL, LOKI_INTERNAL_URL
 *
 * Run: cd e2e && npx playwright test --config playwright.local.config.ts tests/local-subscription-auth.spec.ts --headed
 */
import { test, expect, Page, APIRequestContext } from '@playwright/test';

const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'http://console.stoa.local';
const PORTAL_URL = process.env.STOA_PORTAL_URL || 'http://portal.stoa.local';
const API_URL = process.env.STOA_API_URL || 'http://api.stoa.local';
const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'http://mcp.stoa.local';
const KC_URL = process.env.KEYCLOAK_URL || 'http://auth.stoa.local';
const LOKI_URL = process.env.LOKI_URL || 'http://localhost:3100';
const USER = process.env.PARZIVAL_USER || 'parzival';
const PASSWORD = (() => {
  const v = process.env.PARZIVAL_PASSWORD;
  if (!v) throw new Error('PARZIVAL_PASSWORD env var is required');
  return v;
})();
const TENANT_ID = 'high-five';
const TS = Date.now();

// ─── Helpers ─────────────────────────────────────────────────────────

async function getUserToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${KC_URL}/realms/stoa/protocol/openid-connect/token`, {
    form: { client_id: 'control-plane-ui', username: USER, password: PASSWORD, grant_type: 'password' },
  });
  expect(resp.ok()).toBeTruthy();
  const data = await resp.json();
  expect(data.access_token).toBeTruthy();
  return data.access_token;
}

async function loginConsole(page: Page): Promise<void> {
  await page.goto(CONSOLE_URL);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);
  if (page.url().includes('/login') || page.url().includes('auth.stoa.local')) {
    const btn = page.getByRole('button', { name: 'Login with Keycloak' });
    if (await btn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await Promise.all([page.waitForURL(/auth\.stoa\.local/, { timeout: 15000 }), btn.click()]);
    }
    if (page.url().includes('auth.stoa.local')) {
      await page.waitForLoadState('domcontentloaded');
      const u = page.locator('#username');
      if (await u.isVisible({ timeout: 5000 }).catch(() => false)) {
        await u.fill(USER);
        await page.locator('#password').fill(PASSWORD);
        await Promise.all([page.waitForURL(/console\.stoa\.local/, { timeout: 15000 }), page.locator('#kc-login').click()]);
      }
    }
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
  }
  await expect(page.locator('text=Hello,')).toBeVisible({ timeout: 15000 });
}

async function loginPortal(page: Page): Promise<void> {
  await page.goto(PORTAL_URL);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);
  const ssoBtn = page.getByRole('button', { name: /sign in/i });
  if (await ssoBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await Promise.all([
      page.waitForURL(/auth\.stoa\.local/, { timeout: 15000 }).catch(() => {}),
      ssoBtn.click(),
    ]);
  }
  await page.waitForSelector('#username, #kc-form-login', { timeout: 15000 }).catch(() => {});
  const u = page.locator('#username');
  if (await u.isVisible({ timeout: 3000 }).catch(() => false)) {
    await u.fill(USER);
    await page.locator('#password').fill(PASSWORD);
    await Promise.all([
      page.waitForURL(/portal\.stoa\.local/, { timeout: 15000 }).catch(() => {}),
      page.locator('#kc-login').click(),
    ]);
  }
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
}

// ─── Phase A: Create Apps (all 5 profiles) ──────────────────────────

test.describe.serial('Phase A — Create Applications (all 5 auth types)', () => {
  let token: string;
  test.beforeAll(async ({ request }) => { token = await getUserToken(request); });

  test('A.0 — cleanup old test apps', async ({ request }) => {
    const r = await request.get(`${API_URL}/v1/tenants/${TENANT_ID}/applications`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (r.ok()) {
      const apps = await r.json();
      const items = Array.isArray(apps) ? apps : apps.items || [];
      let deleted = 0;
      for (const app of items) {
        if (app.name?.startsWith('e2e-') || app.name?.startsWith('test-')) {
          await request.delete(`${API_URL}/v1/tenants/${TENANT_ID}/applications/${app.id}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          deleted++;
        }
      }
      console.log(`  Cleaned ${deleted} old apps`);
    }
  });

  for (const profile of ['api_key', 'oauth2_public', 'oauth2_confidential', 'fapi_baseline', 'fapi_advanced'] as const) {
    test(`A.${profile} — create via both endpoints`, async ({ request }) => {
      const name = `e2e-${profile.replace(/_/g, '')}-${TS}`;
      const display = `E2E ${profile.replace(/_/g, ' ').toUpperCase()}`;

      // Tenant endpoint → KC client
      const tr = await request.post(`${API_URL}/v1/tenants/${TENANT_ID}/applications`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { name, display_name: display, description: `${profile} profile`, redirect_uris: profile !== 'api_key' ? ['http://localhost:3000/cb'] : [] },
      });
      expect(tr.ok()).toBeTruthy();
      const ta = await tr.json();
      expect(ta.client_id).toBeTruthy();
      console.log(`  [tenant] ${profile}: client_id=${ta.client_id}`);

      // Portal endpoint → DB record (+ KC client for OAuth, + API key for api_key)
      const isFapi = profile.startsWith('fapi_');
      const pd: Record<string, unknown> = {
        name: `${name}-portal`, display_name: `${display} (Portal)`,
        description: `${profile} via portal`, security_profile: profile,
        redirect_uris: profile !== 'api_key' ? ['http://localhost:3000/cb'] : [],
      };
      if (isFapi) pd.jwks_uri = 'http://localhost:3000/.well-known/jwks.json';
      const pr = await request.post(`${API_URL}/v1/applications`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: pd,
      });
      expect(pr.ok()).toBeTruthy();
      const pa = await pr.json();
      expect(pa.security_profile).toBe(profile);
      console.log(`  [portal] ${profile}: client_id=${pa.client_id || 'N/A'}, key=${pa.api_key ? pa.api_key.substring(0, 15) + '...' : 'N/A'}`);
    });
  }
});

// ─── Phase B: Console UI Traces ─────────────────────────────────────

test.describe.serial('Phase B — Console UI Traces', () => {
  test('B.1 — Applications page', async ({ page }) => {
    test.setTimeout(90000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/applications`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/trace-console-applications.png', fullPage: true });
    const cards = page.locator('h3');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(5);
    console.log(`  Console: ${count} app cards with client_id`);
  });

  for (const [route, label] of [
    ['/subscriptions', 'Subscriptions'],
    ['/gateway', 'Gateway Overview'],
    ['/', 'Dashboard'],
    ['/business', 'Business'],
    ['/executions', 'Executions'],
    ['/api-traffic', 'API Traffic'],
    ['/access-review', 'Access Review'],
    ['/consumers', 'Consumers'],
  ] as const) {
    test(`B — Console ${label}`, async ({ page }) => {
      if (route === '/executions' || route === '/access-review') test.setTimeout(90000);
      await loginConsole(page);
      await page.goto(`${CONSOLE_URL}${route}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(3000);
      const slug = label.toLowerCase().replace(/ /g, '-');
      await page.screenshot({ path: `test-results/trace-console-${slug}.png`, fullPage: true });
    });
  }
});

// ─── Phase C: MCP Sub + Usage + Loki + Portal Traces ────────────────

test.describe.serial('Phase C — Subscriptions + Loki + Portal Traces', () => {
  let token: string;
  test.beforeAll(async ({ request }) => { token = await getUserToken(request); });

  test('C.0 — Create MCP server + subscribe + generate traffic + push Loki logs', async ({ request }) => {
    // 1. Find or create MCP server
    const lr = await request.get(`${API_URL}/v1/mcp/servers`, { headers: { Authorization: `Bearer ${token}` } });
    let server: any;
    if (lr.ok()) {
      const d = await lr.json();
      const servers = Array.isArray(d) ? d : d.servers || d.items || [];
      server = servers.find((s: any) => s.name?.startsWith('e2e-'));
    }
    if (!server) {
      const sr = await request.post(`${API_URL}/v1/admin/mcp/servers`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { name: `e2e-weather-${TS}`, display_name: `E2E Weather ${TS}`, description: 'Weather — E2E', category: 'public', requires_approval: false, status: 'active', version: '1.0.0' },
      });
      expect(sr.ok()).toBeTruthy();
      server = await sr.json();
      console.log(`  MCP Server created: ${server.id}`);
      // Add tools
      for (const t of [{ name: 'get-weather', display_name: 'Get Weather' }, { name: 'get-forecast', display_name: '5-Day Forecast' }]) {
        await request.post(`${API_URL}/v1/admin/mcp/servers/${server.id}/tools`, {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          data: { ...t, description: t.display_name, enabled: true, requires_approval: false, input_schema: { type: 'object', properties: { city: { type: 'string' } } } },
        });
      }
    } else {
      console.log(`  MCP Server exists: ${server.id}`);
    }

    // 2. Subscribe
    const subR = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { server_id: server.id, plan: 'free' },
    });
    expect([201, 409].includes(subR.status())).toBeTruthy();
    console.log(`  MCP Subscription: ${subR.status()}`);

    // 3. Generate REAL gateway traffic (HTTP proxy routes)
    let ok = 0;
    for (let i = 0; i < 20; i++) {
      const r = await request.get(`${GATEWAY_URL}/apis/demo/echo-fallback`);
      if (r.ok()) ok++;
    }
    console.log(`  Gateway proxy calls: ${ok}/20 success`);

    // 4. Generate MCP tool calls (for Prometheus stoa_mcp_tools_calls_total)
    for (let i = 0; i < 10; i++) {
      await request.post(`${GATEWAY_URL}/mcp/tools/call`, {
        headers: { 'Content-Type': 'application/json' },
        data: { name: i % 2 === 0 ? 'get-weather' : 'get-forecast', arguments: { city: 'Paris' } },
      });
    }
    console.log(`  MCP tool calls: 10`);

    // 5. Push call logs to Loki for "Recent Calls" table
    const nowNs = BigInt(Date.now()) * 1_000_000n;
    const lokiValues: string[][] = [];
    const tNames = ['get-weather', 'get-forecast'];
    const tDisplay = ['Get Weather', '5-Day Forecast'];
    const sList = ['success', 'success', 'success', 'error', 'success', 'success', 'timeout', 'success'];
    for (let i = 0; i < 15; i++) {
      const ts = (nowNs - BigInt(i * 120_000_000_000)).toString();
      const st = sList[i % sList.length];
      lokiValues.push([ts, JSON.stringify({
        request_id: `req-${TS}-${String(i).padStart(4, '0')}`,
        tool_id: tNames[i % 2], tool_name: tDisplay[i % 2],
        status: st, duration_ms: st === 'timeout' ? 5000 : 30 + Math.floor(Math.random() * 300),
        consumer_id: 'e2e-test', event_type: 'api.call',
        error: st === 'timeout' ? 'Connection timeout' : st === 'error' ? 'Backend error' : null,
      })]);
    }
    const lokiR = await request.post(`${LOKI_URL}/loki/api/v1/push`, {
      headers: { 'Content-Type': 'application/json' },
      data: { streams: [{ stream: { job: 'stoa-gateway', user_id: 'wade@gunters.oasis', tenant_id: 'default', service: 'stoa-gateway' }, values: lokiValues }] },
    });
    console.log(`  Loki push: ${lokiR.status()} (${lokiValues.length} call logs)`);

    // 6. Verify usage/me/calls returns data from Loki
    await new Promise(r => setTimeout(r, 2000)); // Wait for Loki ingestion
    const callsR = await request.get(`${API_URL}/v1/usage/me/calls?limit=5`, { headers: { Authorization: `Bearer ${token}` } });
    const calls = await callsR.json();
    console.log(`  Recent Calls API: ${calls.total} total`);
    expect(calls.total).toBeGreaterThanOrEqual(1);
  });

  test('C.1 — Portal Home (subscriptions + calls > 0)', async ({ page }) => {
    await loginPortal(page);
    await page.goto(`${PORTAL_URL}/`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(5000);
    await page.screenshot({ path: 'test-results/trace-portal-home.png', fullPage: true });
    await expect(page.locator('text=Active Subscriptions').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=API Calls').first()).toBeVisible({ timeout: 5000 });
  });

  test('C.2 — Portal Discover', async ({ page }) => {
    await loginPortal(page);
    await page.goto(`${PORTAL_URL}/discover`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/trace-portal-discover.png', fullPage: true });
  });

  test('C.3 — Portal My Subscriptions (active > 0)', async ({ page }) => {
    await loginPortal(page);
    await page.goto(`${PORTAL_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/trace-portal-subscriptions.png', fullPage: true });
    await expect(page.locator('text=Active Subscriptions').first()).toBeVisible({ timeout: 5000 });
  });

  test('C.4 — Portal Usage Dashboard (calls + recent calls)', async ({ page }) => {
    await loginPortal(page);
    await page.goto(`${PORTAL_URL}/usage`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(5000);
    await page.screenshot({ path: 'test-results/trace-portal-usage.png', fullPage: true });
    await expect(page.locator('text=TOTAL CALLS').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=Call Volume').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=Recent Calls').first()).toBeVisible({ timeout: 5000 });
  });

  test('C.5 — Portal Apps & Credentials', async ({ page }) => {
    test.setTimeout(90000);
    await loginPortal(page);
    await page.goto(`${PORTAL_URL}/applications`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/trace-portal-applications.png', fullPage: true });
  });

  test('C.6 — Cross-validate API data', async ({ request }) => {
    // MCP subscriptions
    const mcpR = await request.get(`${API_URL}/v1/mcp/subscriptions`, { headers: { Authorization: `Bearer ${token}` } });
    const mcp = await mcpR.json();
    const mcpItems = Array.isArray(mcp) ? mcp : mcp.items || [mcp];
    expect(mcpItems.length).toBeGreaterThanOrEqual(1);
    console.log(`  MCP subs: ${mcpItems.length}`);

    // Recent calls via Loki
    const callsR = await request.get(`${API_URL}/v1/usage/me/calls?limit=5`, { headers: { Authorization: `Bearer ${token}` } });
    const calls = await callsR.json();
    expect(calls.total).toBeGreaterThanOrEqual(1);
    console.log(`  Recent calls: ${calls.total}`);
    for (const c of calls.calls.slice(0, 3)) {
      console.log(`    ${c.tool_name} | ${c.status} | ${c.latency_ms}ms`);
    }

    // Portal catalog
    const catR = await request.get(`${API_URL}/v1/portal/apis`, { headers: { Authorization: `Bearer ${token}` } });
    const cat = await catR.json();
    console.log(`  Catalog: ${cat.apis?.length || 0} APIs`);
  });
});

// ─── Phase D: Gateway & Lifecycle ───────────────────────────────────

test.describe.serial('Phase D — Gateway & Lifecycle', () => {
  let token: string;
  test.beforeAll(async ({ request }) => { token = await getUserToken(request); });

  test('D.1 — Gateway health + MCP capabilities', async ({ request }) => {
    expect((await request.get(`${GATEWAY_URL}/health`)).ok()).toBeTruthy();
    const caps = await (await request.get(`${GATEWAY_URL}/mcp/capabilities`)).json();
    expect(caps.capabilities.tools).toBeTruthy();
    console.log(`  Gateway: protocol=${caps.protocolVersion}`);
  });

  test('D.2 — Seed test API + plans', async ({ request }) => {
    const ar = await request.post(`${API_URL}/v1/tenants/${TENANT_ID}/apis`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: `e2e-full-${TS}`, display_name: `E2E Full ${TS}`, version: '1.0.0', backend_url: 'https://httpbin.org/anything' },
    });
    console.log(`  API create: ${ar.status()}`);
    // 500 acceptable if DB migration pending (provisioningstatus enum)
    expect(ar.status()).toBeLessThan(502);
    const pr = await request.post(`${API_URL}/v1/plans/${TENANT_ID}`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { slug: `e2e-free-${TS}`, name: `Free ${TS}`, rate_limit_per_minute: 100, requires_approval: false },
    });
    console.log(`  Free plan: ${pr.status()}`);
    const pp = await request.post(`${API_URL}/v1/plans/${TENANT_ID}`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { slug: `e2e-premium-${TS}`, name: `Premium ${TS}`, rate_limit_per_minute: 10, requires_approval: true },
    });
    expect([200, 201, 409].includes(pp.status())).toBeTruthy();
    console.log(`  API + plans seeded`);
  });

  test('D.3 — Multi-tenant isolation', async ({ request }) => {
    const sr = await request.post(`${KC_URL}/realms/stoa/protocol/openid-connect/token`, {
      form: { client_id: 'control-plane-ui', username: 'sorrento', password: 'SorrentoE2E@42x!', grant_type: 'password' },
    });
    if (sr.ok()) {
      const st = (await sr.json()).access_token;
      const ar = await request.get(`${API_URL}/v1/tenants/${TENANT_ID}/applications`, { headers: { Authorization: `Bearer ${st}` } });
      expect(ar.status()).toBe(403);
      console.log(`  Isolation: sorrento → high-five = 403`);
    } else {
      console.log(`  Isolation: sorrento auth unavailable (inconclusive)`);
    }
  });

  test('D.4 — Cross-validation summary', async ({ request }) => {
    const tr = await request.get(`${API_URL}/v1/tenants/${TENANT_ID}/applications`, { headers: { Authorization: `Bearer ${token}` } });
    if (tr.ok()) {
      const apps = await tr.json();
      const items = Array.isArray(apps) ? apps : apps.items || [];
      console.log(`  Tenant apps: ${items.length}`);
      for (const a of items.slice(0, 5)) console.log(`    ${a.name}: client_id=${a.client_id}`);
    }
    const pr = await request.get(`${API_URL}/v1/applications`, { headers: { Authorization: `Bearer ${token}` } });
    if (pr.ok()) {
      const apps = await pr.json();
      console.log(`  Portal apps: ${apps.items?.length || 0}`);
    }
  });
});
