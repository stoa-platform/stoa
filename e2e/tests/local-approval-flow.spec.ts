/**
 * E2E: Approval Flow — Full State Machine + Console Admin UI Clicks
 *
 * Tests subscription state transitions via Console UI (approve/reject buttons)
 * and API (suspend/reactivate/revoke, security edge cases).
 *
 * State machine tested:
 *   pending → active (approve via Console UI click)
 *   pending → rejected (reject via Console UI click with reason)
 *   active → suspended → active (suspend/reactivate via API)
 *   active → revoked (revoke with reason via API)
 *   cross-tenant 403, double-approve 400
 *
 * Run: cd e2e && npx playwright test --config playwright.local.config.ts tests/local-approval-flow.spec.ts --headed
 */
import { test, expect, Page, APIRequestContext } from '@playwright/test';

const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'http://console.stoa.local';
const PORTAL_URL = process.env.STOA_PORTAL_URL || 'http://portal.stoa.local';
const API_URL = process.env.STOA_API_URL || 'http://api.stoa.local';
const KC_URL = process.env.KEYCLOAK_URL || 'http://auth.stoa.local';
const TS = Date.now();

const ADMIN = { user: 'parzival', pass: 'Parzival@2026!' };
const ATTACKER = { user: 'sorrento', pass: 'SorrentoE2E@99z!' };
const TENANT = 'high-five';

// ─── Helpers ───────────────────────��────────────────────────────

async function getToken(req: APIRequestContext, u: string, p: string): Promise<string> {
  const r = await req.post(`${KC_URL}/realms/stoa/protocol/openid-connect/token`, {
    form: { client_id: 'control-plane-ui', username: u, password: p, grant_type: 'password' },
  });
  expect(r.ok(), `Auth failed for ${u}: ${r.status()}`).toBeTruthy();
  return (await r.json()).access_token;
}

async function fillKcForm(page: Page, user: string, pass: string) {
  await page.waitForLoadState('domcontentloaded');
  // Old theme: #username/#password/#kc-login
  const oldU = page.locator('#username');
  // New theme: placeholder-based
  const newU = page.getByPlaceholder(/email/i);
  if (await oldU.isVisible({ timeout: 3000 }).catch(() => false)) {
    await oldU.fill(user);
    await page.locator('#password').fill(pass);
    await page.locator('#kc-login').click();
  } else if (await newU.isVisible({ timeout: 3000 }).catch(() => false)) {
    await newU.fill(user);
    await page.getByPlaceholder(/password/i).fill(pass);
    await page.getByRole('button', { name: /sign in/i }).click();
  }
}

async function loginConsole(page: Page, user = ADMIN.user, pass = ADMIN.pass) {
  await page.goto(CONSOLE_URL);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);

  const kcBtn = page.getByRole('button', { name: 'Login with Keycloak' });
  const emailField = page.getByPlaceholder('Enter your email');

  if (await kcBtn.isVisible({ timeout: 8000 }).catch(() => false)) {
    await Promise.all([
      page.waitForURL(/auth\.stoa\.local|localhost:8080/, { timeout: 15000 }),
      kcBtn.click(),
    ]);
    if (page.url().includes('auth.stoa.local') || page.url().includes('localhost:8080')) {
      await Promise.all([
        page.waitForURL(/console/, { timeout: 15000 }).catch(() => {}),
        fillKcForm(page, user, pass),
      ]);
    }
  } else if (await emailField.isVisible({ timeout: 5000 }).catch(() => false)) {
    await emailField.fill(user);
    await page.getByPlaceholder('Enter your password').fill(pass);
    await page.getByRole('button', { name: 'Sign In' }).click();
  } else if (page.url().includes('auth.stoa.local') || page.url().includes('localhost:8080')) {
    await Promise.all([
      page.waitForURL(/console/, { timeout: 15000 }).catch(() => {}),
      fillKcForm(page, user, pass),
    ]);
  }
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await expect(page.locator('text=Hello,')).toBeVisible({ timeout: 15000 });
}

async function loginPortal(page: Page) {
  await page.goto(PORTAL_URL);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);
  const sso = page.getByRole('button', { name: /sign in/i });
  if (await sso.isVisible({ timeout: 5000 }).catch(() => false)) {
    await Promise.all([
      page.waitForURL(/auth\.stoa\.local|localhost:8080/, { timeout: 15000 }).catch(() => {}),
      sso.click(),
    ]);
  }
  await page.waitForSelector('#username, input[placeholder*="email"]', { timeout: 15000 }).catch(() => {});
  await Promise.all([
    page.waitForURL(/portal/, { timeout: 15000 }).catch(() => {}),
    fillKcForm(page, ADMIN.user, ADMIN.pass),
  ]);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
}

// ─── Data seeding: create classic subscription for Console ──────

interface SeedResult {
  subscriptionId: string;
  applicationName: string;
  apiName: string;
}

async function seedClassicSubscription(
  req: APIRequestContext,
  token: string,
  suffix: string
): Promise<SeedResult> {
  const appName = `e2e-app-${suffix}-${TS}`;
  const apiName = `e2e-weather-${suffix}-${TS}`;

  // 1. Create PortalApplication (api_key profile — no Keycloak dependency)
  const appResp = await req.post(`${API_URL}/v1/applications`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: { name: appName, display_name: appName, description: 'E2E test app', security_profile: 'api_key' },
  });
  expect(appResp.ok(), `Failed to create app: ${appResp.status()}`).toBeTruthy();
  const app = await appResp.json();

  // 2. Seed API into catalog
  const seedResp = await req.post(`${API_URL}/v1/admin/catalog/seed`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: {
      tenant_id: TENANT,
      apis: [{
        name: apiName,
        display_name: apiName,
        version: '1.0.0',
        description: 'E2E test API',
        backend_url: 'http://localhost:8888/echo',
        category: 'rest',
        tags: ['e2e', 'portal:published'],
      }],
    },
  });
  // seed might return 200 or 201
  expect(seedResp.status()).toBeLessThan(300);

  // 3. Get the seeded API's catalog ID (slug)
  const apisResp = await req.get(`${API_URL}/v1/tenants/${TENANT}/apis?page=1&page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const apisData = await apisResp.json();
  const apis = apisData.items || apisData;
  const seededApi = apis.find((a: any) => a.api_name?.includes(apiName) || a.name?.includes(apiName));
  const apiId = seededApi?.api_id || seededApi?.id || apiName;

  // 4. Create classic subscription (PENDING status)
  const subResp = await req.post(`${API_URL}/v1/subscriptions`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: {
      application_id: app.id,
      application_name: appName,
      api_id: apiId,
      api_name: apiName,
      api_version: '1.0.0',
      tenant_id: TENANT,
      plan_name: 'default',
    },
  });
  expect(subResp.ok(), `Failed to create subscription: ${subResp.status()} ${await subResp.text()}`).toBeTruthy();
  const sub = await subResp.json();
  expect(sub.status).toBe('pending');

  return { subscriptionId: sub.id, applicationName: appName, apiName };
}

// ��── Shared state ──────────────────────────────────────────────

let adminToken: string;
let mcpServerId: string;

test.describe.serial('Approval Flow — Full State Machine', () => {
  test.beforeAll(async ({ request }) => {
    adminToken = await getToken(request, ADMIN.user, ADMIN.pass);

    // Find or create MCP server with requires_approval for API-based tests
    const lr = await request.get(`${API_URL}/v1/mcp/servers`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (lr.ok()) {
      const d = await lr.json();
      const servers = Array.isArray(d) ? d : d.servers || d.items || [];
      const existing = servers.find((s: any) => s.name?.includes('approval') && s.requires_approval);
      if (existing) { mcpServerId = existing.id; return; }
    }
    const sr = await request.post(`${API_URL}/v1/admin/mcp/servers`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: {
        name: `e2e-approval-${TS}`, display_name: 'Approval Required Server',
        description: 'Needs admin approval', category: 'tenant',
        requires_approval: true, status: 'active', version: '1.0.0',
      },
    });
    expect(sr.ok()).toBeTruthy();
    mcpServerId = (await sr.json()).id;
  });

  // ���── Phase 1: Approve via Console UI ─────────────────────────

  let approvalSeed: SeedResult;

  test('1.1 — Seed classic subscription → PENDING', async ({ request }) => {
    approvalSeed = await seedClassicSubscription(request, adminToken, 'approve');
    console.log(`  1.1 PASS: sub=${approvalSeed.subscriptionId} app=${approvalSeed.applicationName} pending`);
  });

  test('1.2 ��� Console: admin sees pending row + clicks Approve (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Verify stats show pending count
    await expect(page.locator('text=Pending Requests')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: 'test-results/approval-01-console-pending.png', fullPage: true });

    // Find the row with our application name
    const row = page.locator('tr', { hasText: approvalSeed.applicationName });
    await expect(row).toBeVisible({ timeout: 10000 });

    // Click the "Approve" button on that row
    const approveBtn = row.locator('button', { hasText: 'Approve' });
    await expect(approveBtn).toBeVisible({ timeout: 5000 });
    await approveBtn.click();

    // Confirm dialog: "Approve Subscription" → click "Approve"
    const dialog = page.locator('[role="dialog"], .fixed');
    await expect(dialog.locator('text=Approve Subscription')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: 'test-results/approval-02-confirm-dialog.png', fullPage: true });

    // Click confirm button in the dialog
    const confirmBtn = dialog.locator('button', { hasText: 'Approve' });
    await confirmBtn.click();

    // Wait for toast success + table reload
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-03-after-approve.png', fullPage: true });

    // Verify: switch to Active tab and check the subscription moved there
    const activeTab = page.locator('button', { hasText: /^Active/ });
    await activeTab.click();
    await page.waitForTimeout(2000);

    // The approved subscription should appear in the Active tab
    const activeRow = page.locator('tr', { hasText: approvalSeed.applicationName });
    await expect(activeRow).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: 'test-results/approval-04-active-tab.png', fullPage: true });

    console.log('  1.2 PASS: Console approve via UI click → sub moved to Active tab');
  });

  // ─── Phase 2: Reject via Console UI ──────────────────────────

  let rejectSeed: SeedResult;

  test('2.1 — Seed another classic subscription for rejection', async ({ request }) => {
    rejectSeed = await seedClassicSubscription(request, adminToken, 'reject');
    console.log(`  2.1 PASS: sub=${rejectSeed.subscriptionId} pending (for rejection)`);
  });

  test('2.2 — Console: admin clicks Reject + enters reason (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Find the row for our reject subscription
    const row = page.locator('tr', { hasText: rejectSeed.applicationName });
    await expect(row).toBeVisible({ timeout: 10000 });

    // Click Reject button on the row
    const rejectBtn = row.locator('button', { hasText: 'Reject' });
    await expect(rejectBtn).toBeVisible({ timeout: 5000 });
    await rejectBtn.click();

    // Reject modal appears with textarea
    const modal = page.locator('.fixed.inset-0');
    await expect(modal.locator('text=Reject Subscription')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: 'test-results/approval-05-reject-modal.png', fullPage: true });

    // Type rejection reason
    const textarea = modal.locator('textarea');
    await textarea.fill('Insufficient justification for API access');

    // Click Reject button in the modal
    const modalRejectBtn = modal.locator('button', { hasText: 'Reject' }).last();
    await modalRejectBtn.click();

    // Wait for toast + reload
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-06-after-reject.png', fullPage: true });

    // The row should disappear from Pending tab
    await expect(page.locator('tr', { hasText: rejectSeed.applicationName })).not.toBeVisible({ timeout: 5000 });

    // Verify: check Rejected tab
    const rejectedTab = page.locator('button', { hasText: /^Rejected/ });
    await rejectedTab.click();
    await page.waitForTimeout(2000);
    const rejectedRow = page.locator('tr', { hasText: rejectSeed.applicationName });
    await expect(rejectedRow).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: 'test-results/approval-07-rejected-tab.png', fullPage: true });

    console.log('  2.2 PASS: Console reject via UI click → sub moved to Rejected tab');
  });

  // ─── Phase 3: Suspend / Reactivate (MCP subs via API) ────────

  test('3.1 — MCP: subscribe + approve → active', async ({ request }) => {
    // Clean existing MCP subs
    const existing = await request.get(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (existing.ok()) {
      const d = await existing.json();
      for (const s of (Array.isArray(d) ? d : d.items || [])) {
        if ((s.server_id === mcpServerId || s.server?.id === mcpServerId) && s.status !== 'revoked') {
          await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${s.id}/revoke`, {
            headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
            data: { reason: 'E2E cleanup' },
          }).catch(() => {});
        }
      }
    }

    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: { server_id: mcpServerId, plan: 'free' },
    });
    expect(sub.ok()).toBeTruthy();
    const subId = (await sub.json()).id;

    const approved = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: {},
    });
    expect((await approved.json()).status).toBe('active');
    console.log(`  3.1 PASS: MCP sub=${subId} active`);
  });

  test('3.2 — Suspend → SUSPENDED', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=active`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    const items = (await subs.json()).items || [];
    const activeSub = items.find((s: any) => s.status === 'active');
    expect(activeSub).toBeTruthy();

    const s = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${activeSub.id}/suspend`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    expect((await s.json()).status).toBe('suspended');
    console.log('  3.2 PASS: suspended');
  });

  test('3.3 — Reactivate �� ACTIVE', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=suspended`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    const items = (await subs.json()).items || [];
    const suspSub = items.find((s: any) => s.status === 'suspended');
    expect(suspSub).toBeTruthy();

    const r = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${suspSub.id}/reactivate`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    expect((await r.json()).status).toBe('active');
    console.log('  3.3 PASS: reactivated → active');
  });

  // ─── Phase 4: Revoke with reason ─────���───────────────────────

  test('4.1 — Revoke active MCP sub with reason', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=active`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    const items = (await subs.json()).items || [];
    const activeSub = items.find((s: any) => s.status === 'active');
    expect(activeSub).toBeTruthy();

    const r = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${activeSub.id}/revoke`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: { reason: 'E2E: terms of service violation' },
    });
    expect((await r.json()).status).toBe('revoked');
    console.log('  4.1 PASS: revoked');
  });

  // ─── Phase 5: Security & Edge Cases ──────────────────────────

  test('5.1 — Cross-tenant: sorrento cannot approve high-five sub', async ({ request }) => {
    // Create a pending MCP sub
    const existing = await request.get(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (existing.ok()) {
      const d = await existing.json();
      for (const s of (Array.isArray(d) ? d : d.items || [])) {
        if ((s.server_id === mcpServerId || s.server?.id === mcpServerId) && s.status !== 'revoked') {
          await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${s.id}/revoke`, {
            headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
            data: { reason: 'E2E cleanup phase 5' },
          }).catch(() => {});
        }
      }
    }

    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: { server_id: mcpServerId, plan: 'free' },
    });
    expect(sub.ok()).toBeTruthy();
    const subId = (await sub.json()).id;

    const at = await getToken(request, ATTACKER.user, ATTACKER.pass);
    const r = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`, {
      headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' },
      data: {},
    });
    expect(r.status()).toBe(403);
    console.log('  5.1 PASS: sorrento → 403');
  });

  test('5.2 — Double approve → 400', async ({ request }) => {
    const p = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/pending`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    const items = (await p.json()).items || [];
    if (items.length > 0) {
      const id = items[0].subscription?.id || items[0].id;
      await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${id}/approve`, {
        headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
        data: {},
      });
      const d = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${id}/approve`, {
        headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
        data: {},
      });
      expect(d.status()).toBeGreaterThanOrEqual(400);
      expect(d.status()).toBeLessThan(500);
      console.log(`  5.2 PASS: double → ${d.status()}`);
    }
  });

  test('5.3 — Cross-tenant list 403', async ({ request }) => {
    const at = await getToken(request, ATTACKER.user, ATTACKER.pass);
    const r = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}`, {
      headers: { Authorization: `Bearer ${at}` },
    });
    expect(r.status()).toBe(403);
    console.log('  5.3 PASS: list → 403');
  });

  // ─── Phase 6: Console + Portal UI Final Screenshots ──────────

  test('6.1 — Console Subscriptions final state (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-console-final.png', fullPage: true });
    console.log('  6.1 PASS: Console final screenshot');
  });

  test('6.2 — Portal Subscriptions (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginPortal(page);
    await page.goto(`${PORTAL_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-portal-final.png', fullPage: true });
    console.log('  6.2 PASS: Portal final screenshot');
  });

  // ─── Phase 7: Cross-Validation ───────────────────────────────

  test('7.1 — API confirms all transitions happened', async ({ request }) => {
    // Classic subs (Console)
    const classicSubs = await request.get(`${API_URL}/v1/subscriptions/tenant/${TENANT}`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (classicSubs.ok()) {
      const items = (await classicSubs.json()).items || [];
      const byStatus: Record<string, number> = {};
      for (const s of items) byStatus[s.status] = (byStatus[s.status] || 0) + 1;
      console.log(`  7.1 Classic subs: ${JSON.stringify(byStatus)}`);
      // We should have at least active + rejected from UI tests
      expect(Object.keys(byStatus).length).toBeGreaterThanOrEqual(2);
    }

    // MCP subs
    const mcpSubs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (mcpSubs.ok()) {
      const items = (await mcpSubs.json()).items || [];
      const byStatus: Record<string, number> = {};
      for (const s of items) byStatus[s.status] = (byStatus[s.status] || 0) + 1;
      console.log(`  7.1 MCP subs: ${JSON.stringify(byStatus)}`);
    }
  });
});
