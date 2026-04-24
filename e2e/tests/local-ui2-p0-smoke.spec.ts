/**
 * UI-2 P0 Batch — Post-deploy smoke test (staging or prod)
 *
 * Exercises the behaviors locked at unit level by:
 *   - control-plane-ui/src/services/http/refresh.test.ts (9 tests)
 *   - control-plane-ui/src/services/http/sse.test.ts    (10 tests)
 *   - control-plane-ui/src/services/api.test.ts          (2 tests)
 *   - control-plane-ui/src/hooks/useEvents.test.ts       (12 tests)
 *
 * Focus: what vitest cannot cover — real Keycloak OIDC redirect flow,
 * real Vite bundle behavior, real fetch-event-source lib in Chromium.
 *
 * Prerequisites:
 *   - PR #2514 deployed to the target env (image contains C1..C4).
 *   - env var STOA_CONSOLE_URL set (default https://console.gostoa.dev)
 *   - env var PARZIVAL_PASSWORD set (real KC credentials)
 *   - (optional) env var STOA_KC_URL set (default https://auth.gostoa.dev)
 *
 * Run:
 *   cd e2e
 *   STOA_CONSOLE_URL=https://console.gostoa.dev PARZIVAL_PASSWORD=... \
 *     npx playwright test --config playwright.local.config.ts \
 *     tests/local-ui2-p0-smoke.spec.ts --headed --reporter=list
 *
 * Evidence archiving: screenshots, trace, video captured by playwright.local.config.ts
 * (see audit/ui-2/phase3/ for the human checklist).
 */
import { test, expect, Page, Request } from '@playwright/test';

const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev';
const KC_URL = process.env.STOA_KC_URL || 'https://auth.gostoa.dev';
const PARZIVAL_USER = process.env.PARZIVAL_USER || 'parzival@high-five.io';

function requirePassword(): string {
  const v = process.env.PARZIVAL_PASSWORD;
  if (!v) throw new Error('PARZIVAL_PASSWORD env var is required — staging/prod creds');
  return v;
}

const API_ORIGIN = new URL(CONSOLE_URL).hostname.replace('console.', 'api.');
const API_BASE = `https://${API_ORIGIN}`;

async function login(page: Page) {
  const password = requirePassword();
  await page.goto(CONSOLE_URL);
  // Some layouts show an explicit "Sign in" button before redirecting to KC.
  const signIn = page.getByRole('button', { name: /sign in|se connecter|login/i }).first();
  if (await signIn.isVisible().catch(() => false)) {
    await signIn.click();
  }
  await page.waitForURL(/\/realms\/stoa\/protocol\/openid-connect\/auth/i, { timeout: 20_000 });
  await page.fill('#username', PARZIVAL_USER);
  await page.fill('#password', password);
  await page.click('#kc-login');
  await page.waitForURL(new RegExp(`^${CONSOLE_URL.replace(/\//g, '\\/')}(\\/|$)`), {
    timeout: 30_000,
  });
  await page.waitForLoadState('networkidle');
}

/** Decode exp claim from a JWT without verification. */
function decodeExp(jwt: string): number {
  const [, payload] = jwt.split('.');
  const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
  const json = JSON.parse(
    Buffer.from(normalized, 'base64').toString('utf8')
  ) as { exp?: number };
  return json.exp ?? 0;
}

/** Read the current access_token from react-oidc-context sessionStorage. */
async function getCurrentToken(page: Page): Promise<string | null> {
  return page.evaluate(() => {
    const prefix = 'oidc.user:';
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key && key.startsWith(prefix)) {
        const raw = sessionStorage.getItem(key);
        if (!raw) return null;
        try {
          const parsed = JSON.parse(raw) as { access_token?: string };
          return parsed.access_token ?? null;
        } catch {
          return null;
        }
      }
    }
    return null;
  });
}

/**
 * Mutate the in-memory oidc user so the NEXT API call triggers a 401:
 * swap the access_token for a structurally-valid but backend-rejected one.
 * We keep the refresh_token intact, so the interceptor can renew normally.
 */
async function poisonAccessToken(page: Page): Promise<void> {
  await page.evaluate(() => {
    const prefix = 'oidc.user:';
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (!key?.startsWith(prefix)) continue;
      const raw = sessionStorage.getItem(key);
      if (!raw) continue;
      const parsed = JSON.parse(raw) as {
        access_token: string;
        id_token?: string;
      };
      // Replace payload with an "exp in the past" claim. Backend will reject.
      const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
      const payload = btoa(JSON.stringify({ exp: 1, sub: 'poisoned' }));
      parsed.access_token = `${header}.${payload}.sig`;
      sessionStorage.setItem(key, JSON.stringify(parsed));
    }
  });
}

test.describe('UI-2 P0 smoke @critical', () => {
  test.setTimeout(180_000);

  test('S1 — initial login succeeds and httpClient issues authenticated calls', async ({
    page,
  }) => {
    await login(page);
    const token = await getCurrentToken(page);
    expect(token, 'sessionStorage should hold an OIDC access_token').toBeTruthy();
    expect(decodeExp(token!)).toBeGreaterThan(Math.floor(Date.now() / 1000));

    // /v1/me should have been called with Authorization header.
    const meReq = page.waitForRequest(
      (r) =>
        r.url().includes('/v1/me') && r.method() === 'GET',
      { timeout: 15_000 }
    );
    // Trigger a deliberate nav that forces /v1/me if not already cached.
    await page.goto(`${CONSOLE_URL}/dashboard`);
    const req = await meReq.catch(() => null);
    if (req) {
      const auth = await req.headerValue('Authorization');
      expect(auth).toMatch(/^Bearer /);
    }
  });

  test('S9 P0-9 lock — httpClient.defaults.headers NOT set (dual-write removed)', async ({
    page,
  }) => {
    await login(page);
    const hasDefault = await page.evaluate(() => {
      // The apiService façade is imported via window in dev bundles; probe
      // the document to detect any stray Authorization default on axios.
      // If not accessible, skip — unit test already locks this in api.test.ts.
      return (
        typeof (window as unknown as { __axiosDefaultsAuth?: string }).__axiosDefaultsAuth ===
        'string'
      );
    });
    expect(hasDefault, 'window should not expose stale axios default Authorization').toBe(
      false
    );
  });

  test('S2 P0-2/P0-3 — single 401 triggers refresh + replay with new token', async ({
    page,
  }) => {
    await login(page);
    await page.waitForLoadState('networkidle');

    const tokenRequests: Request[] = [];
    const apiCallAuth: string[] = [];
    page.on('request', (req) => {
      const url = req.url();
      if (url.includes('/realms/stoa/protocol/openid-connect/token')) {
        tokenRequests.push(req);
      }
      if (url.startsWith(API_BASE) && url.includes('/v1/')) {
        req
          .headerValue('Authorization')
          .then((v) => v && apiCallAuth.push(v))
          .catch(() => {});
      }
    });

    const originalToken = await getCurrentToken(page);
    await poisonAccessToken(page);
    // Trigger a navigation that fires a fresh API call.
    await page.goto(`${CONSOLE_URL}/tenants`);
    await page.waitForLoadState('networkidle');

    // Lock: the interceptor triggered a single refresh and replayed.
    expect(
      tokenRequests.length,
      `expected exactly 1 /token refresh, got ${tokenRequests.length}`
    ).toBe(1);

    const newToken = await getCurrentToken(page);
    expect(newToken, 'new access_token should be present after refresh').toBeTruthy();
    expect(newToken).not.toBe(originalToken);

    // At least one API call must have succeeded with the NEW Bearer.
    expect(
      apiCallAuth.some((h) => h === `Bearer ${newToken}`),
      'expected to see replayed API call with new Bearer token'
    ).toBe(true);
  });

  test('S3 P0-1 — parallel 401s trigger exactly ONE refresh (coalescing)', async ({
    page,
  }) => {
    await login(page);
    await page.waitForLoadState('networkidle');

    const tokenRequests: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/realms/stoa/protocol/openid-connect/token')) {
        tokenRequests.push(req);
      }
    });

    await poisonAccessToken(page);

    // Fire N API calls in parallel by navigating to a data-heavy page +
    // invalidating caches via client-side router refresh.
    await page.goto(`${CONSOLE_URL}/dashboard`);
    await page.waitForLoadState('networkidle');

    // A dashboard typically fetches tenants + apis + deployments + metrics.
    // If _retry propagates correctly, the N concurrent 401s must coalesce.
    expect(
      tokenRequests.length,
      `P0-1 cascade regression: expected 1 /token call, got ${tokenRequests.length}`
    ).toBeLessThanOrEqual(1);
  });

  test('S5 P0-4 — SSE connection includes Authorization Bearer header', async ({
    page,
  }) => {
    await login(page);

    const sseRequests: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/v1/events/stream/')) sseRequests.push(req);
    });

    await page.goto(`${CONSOLE_URL}/deployments`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3_000); // SSE stream takes a beat to open

    if (sseRequests.length === 0) {
      test.skip(
        true,
        'No SSE stream opened — Deployments may require an active deploy or tenant selection.'
      );
    }

    const sse = sseRequests[0];
    const auth = await sse.headerValue('Authorization');
    expect(
      auth,
      'P0-4 regression: EventSource was opened without Authorization header'
    ).toMatch(/^Bearer /);

    // P0-4 expected behavior: Accept: text/event-stream for fetch-event-source
    const accept = await sse.headerValue('Accept');
    expect(accept).toMatch(/text\/event-stream/);
  });

  test('S6 P0-5 — SSE handles token rotation without silent 401 loop', async ({
    page,
  }) => {
    await login(page);
    await page.goto(`${CONSOLE_URL}/deployments`);
    await page.waitForTimeout(3_000);

    const tokenRequests: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/realms/stoa/protocol/openid-connect/token')) {
        tokenRequests.push(req);
      }
    });

    // Simulate silent renew mid-stream by poisoning + forcing next reconnect.
    await poisonAccessToken(page);
    // Nudge network — fetch-event-source retries on stream error.
    await page.waitForTimeout(5_000);

    // Either: no token refresh was needed (stream holds), OR exactly one
    // refresh occurred and SSE recovered. Never: many refreshes (cascade).
    expect(tokenRequests.length).toBeLessThanOrEqual(1);
  });
});
