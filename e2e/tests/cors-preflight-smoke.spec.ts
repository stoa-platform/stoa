/**
 * CORS preflight smoke test (CAB-2142).
 *
 * Hits the Control Plane API with a raw CORS preflight from the two personas
 * that matter in prod:
 *   - a known-good origin (console) → must receive Access-Control-Allow-Origin
 *   - an unknown origin (evil) → must NOT receive Access-Control-Allow-Origin
 *
 * Also asserts that the response does not echo TRACE as an allowed method.
 *
 * Runs under the `smoke-api` Playwright project (baseURL = STOA_API_URL).
 * This is the post-deploy non-regression gate for CAB-2142; the unit-level
 * coverage lives in control-plane-api/tests/test_regression_cab_2142_cors.py.
 */
import { expect, test } from '@playwright/test';

const API_URL = process.env.STOA_API_URL || 'https://api.gostoa.dev';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev';
const EVIL_ORIGIN = 'https://evil.example';

// Endpoint chosen because it is cheap (no DB), always reachable, and returns
// 401 on GET (which is fine — we only read the CORS headers, not the body).
const PROBE_PATH = '/v1/me';

test.describe('@smoke CORS preflight — CAB-2142', () => {
  test('allowed origin receives Access-Control-Allow-Origin', async ({ request }) => {
    const response = await request.fetch(`${API_URL}${PROBE_PATH}`, {
      method: 'OPTIONS',
      headers: {
        Origin: CONSOLE_URL,
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'Authorization',
      },
    });

    expect(response.status()).toBeLessThan(400);
    const acao = response.headers()['access-control-allow-origin'];
    expect(acao).toBe(CONSOLE_URL);

    const allowMethods = response.headers()['access-control-allow-methods'] || '';
    expect(allowMethods).toContain('GET');
    // Wildcards must not leak back through the response.
    expect(allowMethods).not.toContain('*');
  });

  test('unknown origin does not receive Access-Control-Allow-Origin', async ({ request }) => {
    const response = await request.fetch(`${API_URL}${PROBE_PATH}`, {
      method: 'OPTIONS',
      headers: {
        Origin: EVIL_ORIGIN,
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'Authorization',
      },
    });

    const acao = response.headers()['access-control-allow-origin'];
    expect(acao).toBeFalsy();
  });

  test('TRACE is never echoed in Allow-Methods', async ({ request }) => {
    const response = await request.fetch(`${API_URL}${PROBE_PATH}`, {
      method: 'OPTIONS',
      headers: {
        Origin: CONSOLE_URL,
        'Access-Control-Request-Method': 'TRACE',
      },
    });

    const allowMethods = response.headers()['access-control-allow-methods'] || '';
    expect(allowMethods).not.toContain('TRACE');
  });
});
