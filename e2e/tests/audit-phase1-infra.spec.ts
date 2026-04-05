/**
 * Audit Phase 1 — Infrastructure Verification (CAB-1970)
 *
 * 8 binary assertions proving the local platform is operational.
 *
 * Run:
 *   cd e2e && npx playwright test --config playwright.audit.config.ts audit-phase1
 */
import { test, expect } from '@playwright/test';
import { loginAndGetToken } from '../fixtures/audit-auth';

const API_URL = process.env.STOA_API_URL || 'http://localhost:8000';
const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'http://localhost:8081';
const KC_URL = process.env.KEYCLOAK_URL || 'http://localhost:8080';
const PROMETHEUS_URL = process.env.PROMETHEUS_URL || 'http://localhost:9090';
const GRAFANA_URL = process.env.GRAFANA_URL || 'http://localhost:3001';
const REDPANDA_ADMIN_URL = process.env.REDPANDA_ADMIN_URL || 'http://localhost:9644';

let authToken: string;

test.describe('Audit Phase 1 — Infrastructure', () => {
  test.describe.configure({ mode: 'serial' });

  test('1.1 — Gateway health endpoint returns 200', async ({ request }) => {
    const resp = await request.get(`${GATEWAY_URL}/health`);
    expect(resp.status()).toBe(200);
    const body = await resp.text();
    expect(body.trim()).toBe('OK');
  });

  test('1.2 — Keycloak stoa realm is accessible', async ({ request }) => {
    const resp = await request.get(`${KC_URL}/realms/stoa`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.realm).toBe('stoa');
  });

  test('1.3 — Console login as parzival succeeds', async ({ page }) => {
    authToken = await loginAndGetToken(page);
    expect(authToken, 'Failed to extract access token from localStorage').toBeTruthy();
    await expect(page.locator('text=Hello,')).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: 'test-results/audit/1.3-console-login.png' });
  });

  test('1.4 — Gateway list contains at least 1 online gateway', async ({ request }) => {
    const resp = await request.get(`${API_URL}/v1/admin/gateways`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    const items = data.items || data;
    expect(Array.isArray(items)).toBeTruthy();
    expect(items.length).toBeGreaterThanOrEqual(1);
    const onlineGw = items.find((g: { status: string }) => g.status === 'online');
    expect(onlineGw, 'No online gateway found').toBeTruthy();
  });

  test('1.5 — Prometheus target for gateway is UP', async ({ request }) => {
    const resp = await request.get(`${PROMETHEUS_URL}/api/v1/targets`);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    const targets = data.data?.activeTargets || [];
    const gwTarget = targets.find(
      (t: { labels: Record<string, string>; health: string }) =>
        (t.labels?.job?.includes('gateway') || t.labels?.instance?.includes('gateway')) &&
        t.health === 'up'
    );
    expect(gwTarget, 'No UP gateway target in Prometheus').toBeTruthy();
  });

  test('1.6 — Grafana is healthy', async ({ request }) => {
    const resp = await request.get(`${GRAFANA_URL}/api/health`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.database).toBe('ok');
  });

  test('1.7 — Redpanda Kafka cluster is healthy', async ({ request }) => {
    const resp = await request.get(`${REDPANDA_ADMIN_URL}/v1/cluster/health_overview`);
    expect(resp.ok(), `Redpanda admin unreachable: ${resp.status()}`).toBeTruthy();
    const health = await resp.json();
    expect(health.is_healthy, 'Redpanda cluster is not healthy').toBe(true);
    expect(health.leaderless_count, 'Redpanda has leaderless partitions').toBe(0);
  });

  test('1.8 — Control Plane API is operational with auth', async ({ request }) => {
    // Verify authenticated API access works end-to-end (KC → token → CP API)
    const resp = await request.get(`${API_URL}/v1/admin/gateways`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(resp.ok(), `API call failed: ${resp.status()}`).toBeTruthy();
    const data = await resp.json();
    const items = data.items || data;
    expect(Array.isArray(items), 'API did not return items array').toBeTruthy();
  });
});
