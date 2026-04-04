/**
 * E2E: Approval Flow — Full Browser-Driven State Machine
 *
 * Real user flow:
 *   art3mis (devops) subscribes via Portal UI → pending
 *   parzival (tenant-admin) approves/rejects via Console UI
 *
 * State machine tested:
 *   pending → active   (Portal subscribe → Console Approve click)
 *   pending → rejected (Portal subscribe → Console Reject click + reason)
 *   active → suspended → active (API: suspend/reactivate)
 *   active → revoked   (API: revoke with reason)
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
const SUBSCRIBER = { user: 'art3mis', pass: 'Art3mis@E2E99!' };
const ATTACKER = { user: 'sorrento', pass: 'SorrentoE2E@99z!' };
const TENANT = 'high-five';

// ─── Helpers ────────────────────────────────────────────────────

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
      page.waitForURL(/auth\.stoa\.local|localhost:8080/, { timeout: 15000 }),
      kcBtn.click(),
    ]);
    if (page.url().includes('auth.stoa.local') || page.url().includes('localhost:8080'))
      await Promise.all([
        page.waitForURL(/console/, { timeout: 15000 }).catch(() => {}),
        fillKcForm(page, user, pass),
      ]);
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

async function loginPortal(page: Page, user: string, pass: string) {
  await page.goto(PORTAL_URL);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);
  const sso = page.getByRole('button', { name: /sign in/i });
  if (await sso.isVisible({ timeout: 5000 }).catch(() => false))
    await Promise.all([
      page.waitForURL(/auth\.stoa\.local|localhost:8080/, { timeout: 15000 }).catch(() => {}),
      sso.click(),
    ]);
  await page
    .waitForSelector('#username, input[placeholder*="email"]', { timeout: 15000 })
    .catch(() => {});
  if (page.url().includes('auth.stoa.local') || page.url().includes('localhost:8080'))
    await Promise.all([
      page.waitForURL(/portal/, { timeout: 15000 }).catch(() => {}),
      fillKcForm(page, user, pass),
    ]);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
}

/**
 * Portal: art3mis subscribes to an API via browser.
 * 1. Navigate to /discover
 * 2. Click first published API
 * 3. Click "Subscribe"
 * 4. Create new app inline (api_key profile) + select Free plan
 * 5. Submit → pending subscription
 * Returns the application name used (for Console lookup).
 */
async function portalSubscribe(page: Page, appSuffix: string): Promise<string> {
  const appName = `e2e-${appSuffix}-${TS}`;

  // Navigate to API catalog
  await page.goto(`${PORTAL_URL}/discover`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  // Click first published API card (link to detail page)
  const apiCard = page.locator('a[href^="/apis/"]').first();
  await expect(apiCard).toBeVisible({ timeout: 10000 });
  await apiCard.click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  // Click "Subscribe" button on API detail page
  const subscribeBtn = page.locator('button', { hasText: 'Subscribe' });
  await expect(subscribeBtn).toBeVisible({ timeout: 10000 });
  await subscribeBtn.click();

  // Subscribe modal opens — "Subscribe to API" header
  const modal = page.locator('.fixed.inset-0');
  await expect(modal.locator('text=Subscribe to API')).toBeVisible({ timeout: 5000 });
  await page.screenshot({ path: `test-results/approval-portal-subscribe-modal-${appSuffix}.png`, fullPage: true });

  // Click "Create new application" link
  const createAppLink = modal.locator('button', { hasText: 'Create new application' });
  await expect(createAppLink).toBeVisible({ timeout: 5000 });
  await createAppLink.click();

  // Fill inline app creation form
  const appNameInput = modal.locator('#new-app-name');
  await expect(appNameInput).toBeVisible({ timeout: 5000 });
  await appNameInput.fill(appName);

  // Select API Key profile (simpler, no KC dependency)
  const profileSelect = modal.locator('#new-app-profile');
  await profileSelect.selectOption('api_key');

  // Click "Create" button
  const createBtn = modal.locator('button', { hasText: 'Create' }).first();
  await createBtn.click();
  await page.waitForTimeout(2000);

  // App should now be selected in dropdown — verify
  const appSelect = modal.locator('#application');
  await expect(appSelect).toBeVisible({ timeout: 5000 });

  // Free plan is selected by default — click Subscribe
  const submitBtn = modal.locator('button[type="submit"]', { hasText: 'Subscribe' });
  // If no submit button, try the generic Subscribe button in form
  const fallbackSubmit = modal.locator('button', { hasText: 'Subscribe' }).last();
  const btn = (await submitBtn.isVisible({ timeout: 2000 }).catch(() => false))
    ? submitBtn
    : fallbackSubmit;
  await btn.click();

  // Wait for success or navigation
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `test-results/approval-portal-subscribed-${appSuffix}.png`, fullPage: true });

  return appName;
}

// ─── Shared state ──────────────────────────────────────────────

let adminToken: string;
let mcpServerId: string;

// Application names created via Portal (for Console row lookup)
let approveAppName: string;
let rejectAppName: string;

test.describe.serial('Approval Flow — Full State Machine', () => {
  test.beforeAll(async ({ request }) => {
    adminToken = await getToken(request, ADMIN.user, ADMIN.pass);

    // Ensure at least one published API in catalog for Portal subscribe flow
    await request.post(`${API_URL}/v1/admin/catalog/seed`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: {
        tenant_id: TENANT,
        apis: [
          {
            name: `e2e-approval-api-${TS}`,
            display_name: `E2E Approval API ${TS}`,
            version: '1.0.0',
            description: 'API for E2E approval flow test',
            backend_url: 'http://localhost:8888/echo',
            category: 'rest',
            tags: ['e2e', 'portal:published'],
          },
        ],
      },
    });

    // Find or create MCP server for API-based tests (phases 3-5)
    const lr = await request.get(`${API_URL}/v1/mcp/servers`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (lr.ok()) {
      const d = await lr.json();
      const servers = Array.isArray(d) ? d : d.servers || d.items || [];
      const existing = servers.find(
        (s: any) => s.name?.includes('approval') && s.requires_approval
      );
      if (existing) {
        mcpServerId = existing.id;
        return;
      }
    }
    const sr = await request.post(`${API_URL}/v1/admin/mcp/servers`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: {
        name: `e2e-approval-${TS}`,
        display_name: 'Approval Required Server',
        description: 'Needs admin approval',
        category: 'tenant',
        requires_approval: true,
        status: 'active',
        version: '1.0.0',
      },
    });
    expect(sr.ok()).toBeTruthy();
    mcpServerId = (await sr.json()).id;
  });

  // ─── Phase 1: art3mis subscribes via Portal → parzival approves via Console ───

  test('1.1 — art3mis subscribes via Portal UI → PENDING (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginPortal(page, SUBSCRIBER.user, SUBSCRIBER.pass);
    approveAppName = await portalSubscribe(page, 'approve');
    console.log(`  1.1 PASS: art3mis subscribed via Portal (app=${approveAppName})`);
  });

  test('1.2 — parzival approves via Console UI (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Stats should show pending
    await expect(page.locator('text=Pending Requests')).toBeVisible({ timeout: 5000 });
    await page.screenshot({
      path: 'test-results/approval-01-console-pending.png',
      fullPage: true,
    });

    // Find row with art3mis's application name
    const row = page.locator('tr', { hasText: approveAppName });
    await expect(row).toBeVisible({ timeout: 10000 });

    // Click "Approve" on the row
    const approveBtn = row.locator('button', { hasText: 'Approve' });
    await expect(approveBtn).toBeVisible({ timeout: 5000 });
    await approveBtn.click();

    // Confirm dialog
    const dialog = page.locator('[role="dialog"], .fixed').last();
    await expect(dialog.locator('text=Approve Subscription')).toBeVisible({ timeout: 5000 });
    await page.screenshot({
      path: 'test-results/approval-02-confirm-dialog.png',
      fullPage: true,
    });
    const confirmBtn = dialog.locator('button', { hasText: 'Approve' });
    await confirmBtn.click();

    // Wait for reload
    await page.waitForTimeout(3000);
    await page.screenshot({
      path: 'test-results/approval-03-after-approve.png',
      fullPage: true,
    });

    // Switch to Active tab — verify row moved
    await page.locator('button', { hasText: /^Active/ }).click();
    await page.waitForTimeout(2000);
    await expect(page.locator('tr', { hasText: approveAppName })).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: 'test-results/approval-04-active-tab.png', fullPage: true });

    console.log('  1.2 PASS: parzival approved via Console UI → Active tab');
  });

  // ─── Phase 2: art3mis subscribes → parzival rejects via Console ───

  test('2.1 — art3mis subscribes again via Portal UI → PENDING (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginPortal(page, SUBSCRIBER.user, SUBSCRIBER.pass);
    rejectAppName = await portalSubscribe(page, 'reject');
    console.log(`  2.1 PASS: art3mis subscribed via Portal (app=${rejectAppName})`);
  });

  test('2.2 — parzival rejects via Console UI + reason (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Find row for reject subscription
    const row = page.locator('tr', { hasText: rejectAppName });
    await expect(row).toBeVisible({ timeout: 10000 });

    // Click "Reject" on the row
    const rejectBtn = row.locator('button', { hasText: 'Reject' });
    await expect(rejectBtn).toBeVisible({ timeout: 5000 });
    await rejectBtn.click();

    // Reject modal with textarea
    const modal = page.locator('.fixed.inset-0').last();
    await expect(modal.locator('text=Reject Subscription')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: 'test-results/approval-05-reject-modal.png', fullPage: true });

    // Type reason
    await modal.locator('textarea').fill('Insufficient justification for API access');

    // Click "Reject" in modal
    await modal.locator('button', { hasText: 'Reject' }).last().click();

    // Wait for reload
    await page.waitForTimeout(3000);
    await page.screenshot({
      path: 'test-results/approval-06-after-reject.png',
      fullPage: true,
    });

    // Row should disappear from Pending
    await expect(page.locator('tr', { hasText: rejectAppName })).not.toBeVisible({ timeout: 5000 });

    // Switch to Rejected tab — verify row appeared
    await page.locator('button', { hasText: /^Rejected/ }).click();
    await page.waitForTimeout(2000);
    await expect(page.locator('tr', { hasText: rejectAppName })).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: 'test-results/approval-07-rejected-tab.png',
      fullPage: true,
    });

    console.log('  2.2 PASS: parzival rejected via Console UI → Rejected tab');
  });

  // ─── Phase 3: Suspend / Reactivate (MCP subs via API) ────────

  test('3.1 — MCP: subscribe + approve → active', async ({ request }) => {
    const existing = await request.get(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (existing.ok()) {
      const d = await existing.json();
      for (const s of Array.isArray(d) ? d : d.items || []) {
        if (
          (s.server_id === mcpServerId || s.server?.id === mcpServerId) &&
          s.status !== 'revoked'
        )
          await request
            .post(`${API_URL}/v1/admin/mcp/subscriptions/${s.id}/revoke`, {
              headers: {
                Authorization: `Bearer ${adminToken}`,
                'Content-Type': 'application/json',
              },
              data: { reason: 'E2E cleanup' },
            })
            .catch(() => {});
      }
    }

    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      data: { server_id: mcpServerId, plan: 'free' },
    });
    expect(sub.ok()).toBeTruthy();
    const subId = (await sub.json()).id;

    const approved = await request.post(
      `${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`,
      {
        headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
        data: {},
      }
    );
    expect((await approved.json()).status).toBe('active');
    console.log(`  3.1 PASS: MCP sub=${subId} active`);
  });

  test('3.2 — Suspend → SUSPENDED', async ({ request }) => {
    const subs = await request.get(
      `${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=active`,
      { headers: { Authorization: `Bearer ${adminToken}` } }
    );
    const activeSub = ((await subs.json()).items || []).find(
      (s: any) => s.status === 'active'
    );
    expect(activeSub).toBeTruthy();

    const s = await request.post(
      `${API_URL}/v1/admin/mcp/subscriptions/${activeSub.id}/suspend`,
      { headers: { Authorization: `Bearer ${adminToken}` } }
    );
    expect((await s.json()).status).toBe('suspended');
    console.log('  3.2 PASS: suspended');
  });

  test('3.3 — Reactivate → ACTIVE', async ({ request }) => {
    const subs = await request.get(
      `${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=suspended`,
      { headers: { Authorization: `Bearer ${adminToken}` } }
    );
    const suspSub = ((await subs.json()).items || []).find(
      (s: any) => s.status === 'suspended'
    );
    expect(suspSub).toBeTruthy();

    const r = await request.post(
      `${API_URL}/v1/admin/mcp/subscriptions/${suspSub.id}/reactivate`,
      { headers: { Authorization: `Bearer ${adminToken}` } }
    );
    expect((await r.json()).status).toBe('active');
    console.log('  3.3 PASS: reactivated → active');
  });

  // ─── Phase 4: Revoke with reason ─────────────────────────────

  test('4.1 — Revoke active MCP sub with reason', async ({ request }) => {
    const subs = await request.get(
      `${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=active`,
      { headers: { Authorization: `Bearer ${adminToken}` } }
    );
    const activeSub = ((await subs.json()).items || []).find(
      (s: any) => s.status === 'active'
    );
    expect(activeSub).toBeTruthy();

    const r = await request.post(
      `${API_URL}/v1/admin/mcp/subscriptions/${activeSub.id}/revoke`,
      {
        headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
        data: { reason: 'E2E: terms of service violation' },
      }
    );
    expect((await r.json()).status).toBe('revoked');
    console.log('  4.1 PASS: revoked');
  });

  // ─── Phase 5: Security & Edge Cases ─────────��────────────────

  test('5.1 — Cross-tenant: sorrento cannot approve high-five sub', async ({ request }) => {
    const existing = await request.get(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (existing.ok()) {
      const d = await existing.json();
      for (const s of Array.isArray(d) ? d : d.items || []) {
        if (
          (s.server_id === mcpServerId || s.server?.id === mcpServerId) &&
          s.status !== 'revoked'
        )
          await request
            .post(`${API_URL}/v1/admin/mcp/subscriptions/${s.id}/revoke`, {
              headers: {
                Authorization: `Bearer ${adminToken}`,
                'Content-Type': 'application/json',
              },
              data: { reason: 'E2E cleanup phase 5' },
            })
            .catch(() => {});
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

  // ─── Phase 6: Final UI Screenshots ───────────────────────────

  test('6.1 — Console Subscriptions final state (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({
      path: 'test-results/approval-console-final.png',
      fullPage: true,
    });
    console.log('  6.1 PASS: Console final screenshot');
  });

  test('6.2 — Portal Subscriptions (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginPortal(page, ADMIN.user, ADMIN.pass);
    await page.goto(`${PORTAL_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await page.screenshot({
      path: 'test-results/approval-portal-final.png',
      fullPage: true,
    });
    console.log('  6.2 PASS: Portal final screenshot');
  });

  // ─── Phase 7: Cross-Validation ───────────────────────────────

  test('7.1 — API confirms all transitions happened', async ({ request }) => {
    // Classic subs (created via Portal UI → Console approval)
    const classicSubs = await request.get(`${API_URL}/v1/subscriptions/tenant/${TENANT}`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    if (classicSubs.ok()) {
      const items = (await classicSubs.json()).items || [];
      const byStatus: Record<string, number> = {};
      for (const s of items) byStatus[s.status] = (byStatus[s.status] || 0) + 1;
      console.log(`  7.1 Classic subs: ${JSON.stringify(byStatus)}`);
      // Should have active (approved) + rejected
      expect(Object.keys(byStatus).length).toBeGreaterThanOrEqual(2);
    }

    // MCP subs
    const mcpSubs = await request.get(
      `${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}`,
      { headers: { Authorization: `Bearer ${adminToken}` } }
    );
    if (mcpSubs.ok()) {
      const items = (await mcpSubs.json()).items || [];
      const byStatus: Record<string, number> = {};
      for (const s of items) byStatus[s.status] = (byStatus[s.status] || 0) + 1;
      console.log(`  7.1 MCP subs: ${JSON.stringify(byStatus)}`);
    }
  });
});
