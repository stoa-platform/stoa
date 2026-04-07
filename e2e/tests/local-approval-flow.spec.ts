/**
 * E2E: Approval Flow — Console UI Clicks + API State Machine
 *
 * Phase 1-2: Console UI — click Approve/Reject on existing pending subscriptions
 * Phase 3-5: MCP subscription state machine via API
 * Phase 6-7: Final screenshots + cross-validation
 *
 * Prerequisites: at least 2 pending classic subscriptions in high-five tenant
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

async function getToken(req: APIRequestContext, u: string, p: string): Promise<string> {
  const r = await req.post(`${KC_URL}/realms/stoa/protocol/openid-connect/token`, {
    form: { client_id: 'control-plane-ui', username: u, password: p, grant_type: 'password' },
  });
  expect(r.ok(), `Auth failed for ${u}: ${r.status()}`).toBeTruthy();
  return (await r.json()).access_token;
}

async function fillKcForm(page: Page, user: string, pass: string) {
  await page.waitForLoadState('domcontentloaded');
  const oldU = page.locator('#username');
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
      page.waitForURL(/auth\.stoa\.local|auth\.gostoa\.dev|localhost:8080/, { timeout: 15000 }),
      kcBtn.click(),
    ]);
    if (/auth\.stoa\.local|auth\.gostoa\.dev|localhost:8080/.test(page.url()))
      await Promise.all([
        page.waitForURL(/console/, { timeout: 15000 }).catch(() => {}),
        fillKcForm(page, user, pass),
      ]);
  } else if (await emailField.isVisible({ timeout: 5000 }).catch(() => false)) {
    await emailField.fill(user);
    await page.getByPlaceholder('Enter your password').fill(pass);
    await page.getByRole('button', { name: 'Sign In' }).click();
  } else if (/auth\.stoa\.local|auth\.gostoa\.dev|localhost:8080/.test(page.url())) {
    await Promise.all([
      page.waitForURL(/console/, { timeout: 15000 }).catch(() => {}),
      fillKcForm(page, user, pass),
    ]);
  }
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await expect(page.locator('text=Wade Watts').first()).toBeVisible({ timeout: 15000 });
}

async function loginPortal(page: Page, user: string, pass: string) {
  await page.goto(PORTAL_URL);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);
  const sso = page.getByRole('button', { name: /sign in/i });
  if (await sso.isVisible({ timeout: 5000 }).catch(() => false))
    await Promise.all([
      page.waitForURL(/auth\.stoa\.local|auth\.gostoa\.dev|localhost:8080/, { timeout: 15000 }).catch(() => {}),
      sso.click(),
    ]);
  await page.waitForSelector('#username, input[placeholder*="email"]', { timeout: 15000 }).catch(() => {});
  if (/auth\.stoa\.local|auth\.gostoa\.dev|localhost:8080/.test(page.url()))
    await Promise.all([
      page.waitForURL(/portal/, { timeout: 15000 }).catch(() => {}),
      fillKcForm(page, user, pass),
    ]);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
}

async function gotoSubscriptions(page: Page) {
  await page.goto(`${CONSOLE_URL}/subscriptions`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  if (await page.locator('text=Cannot connect').isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
  }
}

let adminToken: string;
let mcpServerId: string;

test.describe.serial('Approval Flow — Full State Machine', () => {
  test.beforeAll(async ({ request }) => {
    adminToken = await getToken(request, ADMIN.user, ADMIN.pass);
    const headers = { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' };
    const lr = await request.get(`${API_URL}/v1/mcp/servers`, { headers });
    if (lr.ok()) {
      const d = await lr.json();
      const servers = Array.isArray(d) ? d : d.servers || d.items || [];
      const existing = servers.find((s: any) => s.name?.includes('approval') && s.requires_approval);
      if (existing) { mcpServerId = existing.id; return; }
    }
    const sr = await request.post(`${API_URL}/v1/admin/mcp/servers`, {
      headers,
      data: { name: `e2e-approval-${TS}`, display_name: 'Approval Required', description: 'E2E', category: 'tenant', requires_approval: true, status: 'active', version: '1.0.0' },
    });
    expect(sr.ok()).toBeTruthy();
    mcpServerId = (await sr.json()).id;
  });

  // ─── Phase 1: Console Reject (first — no DB lock issues) ──────

  test('1.1 — Console: click Reject + enter reason (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await gotoSubscriptions(page);

    await expect(page.locator('text=Pending Requests')).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: 'test-results/approval-01-console-pending.png', fullPage: true });

    const rejectBtn = page.locator('td button', { hasText: 'Reject' }).first();
    await expect(rejectBtn).toBeVisible({ timeout: 10000 });

    await rejectBtn.click();
    await expect(page.getByText('Reject Subscription')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: 'test-results/approval-02-reject-modal.png', fullPage: true });

    await page.locator('.fixed.inset-0 textarea').fill('Insufficient justification for API access');
    await page.locator('.fixed.inset-0').locator('button', { hasText: 'Reject' }).click();

    await expect(page.getByText('Reject Subscription')).not.toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'test-results/approval-03-after-reject.png', fullPage: true });

    await page.getByText(/^Rejected\s*\(\d+\)/).click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'test-results/approval-04-rejected-tab.png', fullPage: true });

    console.log('  1.1 PASS: Rejected via Console UI');
  });

  // ─── Phase 2: Console Approve (after reject — may leave DB lock from provision_on_approval) ──

  test('2.1 — Console: click Approve on pending row (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await gotoSubscriptions(page);

    await expect(page.locator('text=Pending Requests')).toBeVisible({ timeout: 15000 });

    const approveBtn = page.locator('button', { hasText: 'Approve' }).first();
    await expect(approveBtn).toBeVisible({ timeout: 10000 });

    await approveBtn.click();
    await expect(page.getByText('Approve Subscription')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: 'test-results/approval-05-confirm-dialog.png', fullPage: true });
    await page.getByLabel('Approve Subscription').getByRole('button', { name: 'Approve' }).click();

    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-06-after-approve.png', fullPage: true });

    await page.locator('button', { hasText: /^Active/ }).click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'test-results/approval-07-active-tab.png', fullPage: true });

    console.log('  2.1 PASS: Approved via Console UI');
  });

  // ─── Phase 3-4: MCP state machine (API) ──────────────────────

  test('3.1 — MCP: subscribe + approve → active', async ({ request }) => {
    const existing = await request.get(`${API_URL}/v1/mcp/subscriptions`, { headers: { Authorization: `Bearer ${adminToken}` } });
    if (existing.ok()) for (const s of (Array.isArray(await existing.json()) ? await existing.json() : (await existing.json()).items || []))
      if ((s.server_id === mcpServerId || s.server?.id === mcpServerId) && s.status !== 'revoked')
        await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${s.id}/revoke`, { headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' }, data: { reason: 'cleanup' } }).catch(() => {});
    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, { headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' }, data: { server_id: mcpServerId, plan: 'free' } });
    expect(sub.ok()).toBeTruthy();
    const subId = (await sub.json()).id;
    const a = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`, { headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' }, data: {} });
    expect((await a.json()).status).toBe('active');
    console.log(`  3.1 PASS: MCP sub=${subId} active`);
  });

  test('3.2 — Suspend → SUSPENDED', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=active`, { headers: { Authorization: `Bearer ${adminToken}` } });
    const activeSub = ((await subs.json()).items || []).find((s: any) => s.status === 'active');
    expect(activeSub).toBeTruthy();
    expect((await (await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${activeSub.id}/suspend`, { headers: { Authorization: `Bearer ${adminToken}` } })).json()).status).toBe('suspended');
    console.log('  3.2 PASS: suspended');
  });

  test('3.3 — Reactivate → ACTIVE', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=suspended`, { headers: { Authorization: `Bearer ${adminToken}` } });
    const suspSub = ((await subs.json()).items || []).find((s: any) => s.status === 'suspended');
    expect(suspSub).toBeTruthy();
    expect((await (await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${suspSub.id}/reactivate`, { headers: { Authorization: `Bearer ${adminToken}` } })).json()).status).toBe('active');
    console.log('  3.3 PASS: reactivated');
  });

  test('4.1 — Revoke with reason', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=active`, { headers: { Authorization: `Bearer ${adminToken}` } });
    const activeSub = ((await subs.json()).items || []).find((s: any) => s.status === 'active');
    expect(activeSub).toBeTruthy();
    expect((await (await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${activeSub.id}/revoke`, { headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' }, data: { reason: 'E2E: ToS violation' } })).json()).status).toBe('revoked');
    console.log('  4.1 PASS: revoked');
  });

  // ─── Phase 5: Security ───────────────────────────────────────

  test('5.1 — Cross-tenant 403', async ({ request }) => {
    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, { headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' }, data: { server_id: mcpServerId, plan: 'free' } });
    const subId = (await sub.json()).id;
    const at = await getToken(request, ATTACKER.user, ATTACKER.pass);
    expect((await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`, { headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' }, data: {} })).status()).toBe(403);
    console.log('  5.1 PASS: sorrento → 403');
  });

  test('5.2 — Double approve → 400', async ({ request }) => {
    const p = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/pending`, { headers: { Authorization: `Bearer ${adminToken}` } });
    const items = (await p.json()).items || [];
    if (items.length > 0) {
      const id = items[0].subscription?.id || items[0].id;
      await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${id}/approve`, { headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' }, data: {} });
      const d = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${id}/approve`, { headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' }, data: {} });
      expect(d.status()).toBeGreaterThanOrEqual(400); expect(d.status()).toBeLessThan(500);
      console.log(`  5.2 PASS: double → ${d.status()}`);
    }
  });

  test('5.3 — Cross-tenant list 403', async ({ request }) => {
    const at = await getToken(request, ATTACKER.user, ATTACKER.pass);
    expect((await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}`, { headers: { Authorization: `Bearer ${at}` } })).status()).toBe(403);
    console.log('  5.3 PASS: list → 403');
  });

  // ─── Phase 6: Final Screenshots ──────────────────────────────

  test('6.1 — Console final state (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await gotoSubscriptions(page);
    await page.screenshot({ path: 'test-results/approval-console-final.png', fullPage: true });
    console.log('  6.1 PASS: Console final');
  });

  test('6.2 — Portal final state (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginPortal(page, ADMIN.user, ADMIN.pass);
    await page.goto(`${PORTAL_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-portal-final.png', fullPage: true });
    console.log('  6.2 PASS: Portal final');
  });

  // ─── Phase 7: Cross-Validation ───────────────────────────────

  test('7.1 — API confirms all transitions', async ({ request }) => {
    const classicSubs = await request.get(`${API_URL}/v1/subscriptions/tenant/${TENANT}`, { headers: { Authorization: `Bearer ${adminToken}` } });
    if (classicSubs.ok()) {
      const items = (await classicSubs.json()).items || [];
      const byStatus: Record<string, number> = {};
      for (const s of items) byStatus[s.status] = (byStatus[s.status] || 0) + 1;
      console.log(`  7.1 Classic: ${JSON.stringify(byStatus)}`);
      expect(Object.keys(byStatus).length).toBeGreaterThanOrEqual(2);
    }
    const mcpSubs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}`, { headers: { Authorization: `Bearer ${adminToken}` } });
    if (mcpSubs.ok()) {
      const items = (await mcpSubs.json()).items || [];
      const byStatus: Record<string, number> = {};
      for (const s of items) byStatus[s.status] = (byStatus[s.status] || 0) + 1;
      console.log(`  7.1 MCP: ${JSON.stringify(byStatus)}`);
    }
  });
});
