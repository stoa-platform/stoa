/**
 * E2E: Approval Flow — Full State Machine + Console Admin Video
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
const SUBSCRIBER = { user: 'art3mis', pass: 'Art3mis@E2E99!' };
const TENANT = 'high-five';

async function getToken(req: APIRequestContext, u: string, p: string) {
  const r = await req.post(`${KC_URL}/realms/stoa/protocol/openid-connect/token`, {
    form: { client_id: 'control-plane-ui', username: u, password: p, grant_type: 'password' },
  });
  expect(r.ok(), `Auth failed for ${u}`).toBeTruthy();
  return (await r.json()).access_token;
}

async function fillKcForm(page: Page, user: string, pass: string) {
  await page.waitForLoadState('domcontentloaded');
  const oldU = page.locator('#username');
  const newU = page.getByPlaceholder(/email/i);
  if (await oldU.isVisible({ timeout: 3000 }).catch(() => false)) {
    await oldU.fill(user); await page.locator('#password').fill(pass); await page.locator('#kc-login').click();
  } else if (await newU.isVisible({ timeout: 3000 }).catch(() => false)) {
    await newU.fill(user); await page.getByPlaceholder(/password/i).fill(pass); await page.getByRole('button', { name: /sign in/i }).click();
  }
}

async function loginConsole(page: Page) {
  await page.goto(CONSOLE_URL); await page.waitForLoadState('domcontentloaded'); await page.waitForTimeout(2000);
  // Console may have its own login form OR redirect to KC
  const kcBtn = page.getByRole('button', { name: 'Login with Keycloak' });
  const emailField = page.getByPlaceholder('Enter your email');
  const signInBtn = page.getByRole('button', { name: 'Sign In' });
  if (await kcBtn.isVisible({ timeout: 8000 }).catch(() => false)) {
    // Old flow: redirect to KC
    await Promise.all([page.waitForURL(/auth.stoa.local|localhost:8080/, { timeout: 15000 }), kcBtn.click()]);
    if ((page.url().includes('auth.stoa.local') || page.url().includes('localhost:8080')))
      await Promise.all([page.waitForURL(/console/, { timeout: 15000 }).catch(() => {}), fillKcForm(page, ADMIN.user, ADMIN.pass)]);
  } else if (await emailField.isVisible({ timeout: 5000 }).catch(() => false)) {
    // New flow: Console's own login form (still talks to KC behind the scenes)
    await emailField.fill(ADMIN.user);
    await page.getByPlaceholder('Enter your password').fill(ADMIN.pass);
    await signInBtn.click();
  } else if ((page.url().includes('auth.stoa.local') || page.url().includes('localhost:8080'))) {
    // Already redirected to KC
    await Promise.all([page.waitForURL(/console/, { timeout: 15000 }).catch(() => {}), fillKcForm(page, ADMIN.user, ADMIN.pass)]);
  }
  await page.waitForLoadState('networkidle'); await page.waitForTimeout(3000);
  await expect(page.locator('text=Hello,')).toBeVisible({ timeout: 15000 });
}

async function loginPortal(page: Page) {
  await page.goto(PORTAL_URL); await page.waitForLoadState('domcontentloaded'); await page.waitForTimeout(2000);
  const sso = page.getByRole('button', { name: /sign in/i });
  if (await sso.isVisible({ timeout: 5000 }).catch(() => false))
    await Promise.all([page.waitForURL(/auth.stoa.local|localhost:8080/, { timeout: 15000 }).catch(() => {}), sso.click()]);
  await page.waitForSelector('#username, input[placeholder*="email"]', { timeout: 15000 }).catch(() => {});
  await Promise.all([page.waitForURL(/portal/, { timeout: 15000 }).catch(() => {}), fillKcForm(page, ADMIN.user, ADMIN.pass)]);
  await page.waitForLoadState('networkidle'); await page.waitForTimeout(3000);
}

let serverId: string, token: string;

test.describe.serial('Approval Flow — Full State Machine', () => {
  test.beforeAll(async ({ request }) => {
    token = await getToken(request, ADMIN.user, ADMIN.pass);
    const lr = await request.get(`${API_URL}/v1/mcp/servers`, { headers: { Authorization: `Bearer ${token}` } });
    if (lr.ok()) {
      const s = (await lr.json() as any[]).find?.((x: any) => x.requires_approval) ||
        ((await lr.json()).servers || (await lr.json()).items || []).find((x: any) => x.requires_approval);
      if (s) { serverId = s.id; return; }
    }
    const sr = await request.post(`${API_URL}/v1/admin/mcp/servers`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: `e2e-approval-${TS}`, display_name: 'Approval Required', description: 'Needs admin', category: 'tenant', requires_approval: true, status: 'active', version: '1.0.0' },
    });
    expect(sr.ok()).toBeTruthy(); serverId = (await sr.json()).id;
    await request.post(`${API_URL}/v1/admin/mcp/servers/${serverId}/tools`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: 'protected', display_name: 'Protected', description: 'Needs approval', enabled: true, requires_approval: false, input_schema: { type: 'object' } },
    });
  });

  async function cleanSubs(req: APIRequestContext) {
    const r = await req.get(`${API_URL}/v1/mcp/subscriptions`, { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok()) return;
    const d = await r.json();
    for (const s of (Array.isArray(d) ? d : d.items || []))
      if ((s.server_id === serverId || s.server?.id === serverId) && s.status !== 'revoked')
        await req.post(`${API_URL}/v1/admin/mcp/subscriptions/${s.id}/revoke`, {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: { reason: 'cleanup' },
        }).catch(() => {});
  }

  test('1.1 — art3mis subscribes → PENDING', async ({ request }) => {
    // art3mis (devops, not admin) subscribes — goes to PENDING
    const subToken = await getToken(request, SUBSCRIBER.user, SUBSCRIBER.pass);
    await cleanSubs(request);
    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${subToken}`, 'Content-Type': 'application/json' },
      data: { server_id: serverId, plan: 'free' },
    });
    // 201 = new, 409 = already pending
    expect([201, 409].includes(sub.status())).toBeTruthy();
    if (sub.status() === 201) {
      const d = await sub.json(); expect(d.status).toBe('pending'); expect(d.api_key).toBeFalsy();
      console.log(`  1.1: art3mis subscribed → pending`);
    } else {
      console.log('  1.1: art3mis already has pending sub (reusing)');
    }
  });

  test('1.2 — Console shows Pending stats + admin approves MCP sub (VIDEO)', async ({ page, request }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Screenshot: Console shows Pending Requests in stats
    await expect(page.locator('text=Pending Requests')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: 'test-results/approval-01-console-pending.png', fullPage: true });

    // Approve the MCP pending sub via API
    const pendingMcp = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/pending`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (pendingMcp.ok()) {
      const items = (await pendingMcp.json()).items || [];
      for (const item of items) {
        const subId = item.subscription?.id || item.id;
        const a = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`, {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: {},
        });
        if (a.ok()) {
          const d = await a.json();
          console.log(`  1.2: Approved MCP sub → key=${d.api_key_prefix}`);
        }
      }
    }

    // Reload Console to show updated stats
    await page.goto(`${CONSOLE_URL}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'test-results/approval-02-console-after-approve.png', fullPage: true });
    console.log('  1.2: Console video captured with pending stats + post-approve');
  });

  test('2.1 — Reject pending via API (Console table has render bug — finding B12)', async ({ request }) => {
    // NOTE: Console Subscriptions table shows "No subscriptions" despite Pending(2) in tabs.
    // This is UI bug B12 — stats count subs but table doesn't render them.
    // Testing rejection via API until table bug is fixed.
    await cleanSubs(request);
    const artToken = await getToken(request, SUBSCRIBER.user, SUBSCRIBER.pass);
    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${artToken}`, 'Content-Type': 'application/json' },
      data: { server_id: serverId, plan: 'free' },
    });
    expect([201, 409].includes(sub.status())).toBeTruthy();
    if (sub.status() === 201) {
      const subId = (await sub.json()).id;
      const r = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/revoke`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { reason: 'E2E: access denied — insufficient justification' },
      });
      expect((await r.json()).status).toBe('revoked');
    }
    console.log('  2.1: rejected via API (Console table bug B12 blocks UI test)');
  });

  test('3.1 — Suspend → Reactivate cycle', async ({ request }) => {
    await cleanSubs(request);
    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: { server_id: serverId, plan: 'free' },
    });
    const subId = (await sub.json()).id;
    await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: {},
    });
    const s = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/suspend`, { headers: { Authorization: `Bearer ${token}` } });
    expect((await s.json()).status).toBe('suspended');
    const r = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/reactivate`, { headers: { Authorization: `Bearer ${token}` } });
    expect((await r.json()).status).toBe('active');
    console.log(`  3.1: active → suspended → active`);
  });

  test('4.1 — Revoke with reason', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}?status=active`, { headers: { Authorization: `Bearer ${token}` } });
    const active = ((await subs.json()).items || []).find((s: any) => s.status === 'active');
    expect(active).toBeTruthy();
    const r = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${active.id}/revoke`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: { reason: 'E2E: ToS violation' },
    });
    expect((await r.json()).status).toBe('revoked'); console.log(`  4.1: revoked`);
  });

  test('5.1 — Cross-tenant 403', async ({ request }) => {
    await cleanSubs(request);
    const sub = await request.post(`${API_URL}/v1/mcp/subscriptions`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: { server_id: serverId, plan: 'free' },
    });
    const subId = (await sub.json()).id;
    const at = await getToken(request, ATTACKER.user, ATTACKER.pass);
    const r = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${subId}/approve`, {
      headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' }, data: {},
    });
    expect(r.status()).toBe(403); console.log(`  5.1: sorrento → 403`);
  });

  test('5.2 — Double approve → 400', async ({ request }) => {
    const p = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/pending`, { headers: { Authorization: `Bearer ${token}` } });
    const items = (await p.json()).items || [];
    if (items.length > 0) {
      const id = items[0].subscription?.id || items[0].id;
      await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${id}/approve`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: {},
      });
      const d = await request.post(`${API_URL}/v1/admin/mcp/subscriptions/${id}/approve`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, data: {},
      });
      expect(d.status()).toBeGreaterThanOrEqual(400); expect(d.status()).toBeLessThan(500);
      console.log(`  5.2: double → ${d.status()}`);
    }
  });

  test('5.3 — Cross-tenant list 403', async ({ request }) => {
    const at = await getToken(request, ATTACKER.user, ATTACKER.pass);
    const r = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}`, { headers: { Authorization: `Bearer ${at}` } });
    expect(r.status()).toBe(403); console.log(`  5.3: list → 403`);
  });

  test('6.1 — Console Subscriptions (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginConsole(page);
    await page.goto(`${CONSOLE_URL}/subscriptions`); await page.waitForLoadState('networkidle'); await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-console-final.png', fullPage: true });
    console.log('  6.1: Console video captured');
  });

  test('6.2 — Portal Subscriptions (VIDEO)', async ({ page }) => {
    test.setTimeout(120000);
    await loginPortal(page);
    await page.goto(`${PORTAL_URL}/subscriptions`); await page.waitForLoadState('networkidle'); await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/approval-portal-final.png', fullPage: true });
    console.log('  6.2: Portal video captured');
  });

  test('7.1 — Cross-validation', async ({ request }) => {
    const subs = await request.get(`${API_URL}/v1/admin/mcp/subscriptions/tenant/${TENANT}`, { headers: { Authorization: `Bearer ${token}` } });
    const items = (await subs.json()).items || [];
    const byStatus: Record<string, number> = {};
    for (const s of items) byStatus[s.status] = (byStatus[s.status] || 0) + 1;
    console.log(`  7.1: ${JSON.stringify(byStatus)}`);
    expect(Object.keys(byStatus).length).toBeGreaterThanOrEqual(2);
  });
});
