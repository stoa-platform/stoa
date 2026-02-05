// =============================================================================
// STOA Platform - API Canary Test
// =============================================================================
// k6 script: Full API flow test for enterprise tier monitoring
// Schedule: Every 15 minutes via k6-operator CronJob
//
// Flow tested:
//   1. Authenticate via Keycloak (client_credentials)
//   2. List API catalog
//   3. List MCP tools
//   4. Invoke a canary MCP tool (stoa-health-check)
//   5. Verify response schema
//
// Prerequisites:
//   - Keycloak service account: stoa-canary-monitor
//   - Canary tool registered: stoa-health-check
// =============================================================================

import http from 'k6/http';
import { check, group, fail } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const canaryErrors = new Counter('stoa_synthetic_canary_errors');
const stepLatency = new Trend('stoa_synthetic_canary_step_latency', true);

const BASE_DOMAIN = __ENV.BASE_DOMAIN || 'gostoa.dev';
const CLIENT_ID = __ENV.CANARY_CLIENT_ID || 'stoa-canary-monitor';
const CLIENT_SECRET = __ENV.CANARY_CLIENT_SECRET || '';

export const options = {
  scenarios: {
    api_canary: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 1,
      maxDuration: '60s',
    },
  },
  thresholds: {
    'checks{step:auth}': ['rate>0.99'],
    'checks{step:catalog}': ['rate>0.99'],
    'checks{step:tools}': ['rate>0.99'],
    http_req_duration: ['p(95)<10000'],
  },
  tags: {
    testType: 'canary',
    platform: 'stoa',
    tier: 'enterprise',
  },
};

export default function () {
  let accessToken = '';

  // -------------------------------------------------------------------------
  // Step 1: Authenticate via Keycloak client_credentials
  // -------------------------------------------------------------------------
  group('1. Authenticate', () => {
    const authUrl = `https://auth.${BASE_DOMAIN}/realms/stoa/protocol/openid-connect/token`;

    const res = http.post(
      authUrl,
      {
        grant_type: 'client_credentials',
        client_id: CLIENT_ID,
        client_secret: CLIENT_SECRET,
        scope: 'openid stoa:read stoa:catalog:read stoa:tools:execute',
      },
      {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        tags: { step: 'auth' },
        timeout: '15s',
      }
    );

    stepLatency.add(res.timings.duration, { step: 'auth' });

    const authPassed = check(
      res,
      {
        auth_success: (r) => r.status === 200,
        has_access_token: (r) => {
          try {
            const body = JSON.parse(r.body);
            return !!body.access_token;
          } catch {
            return false;
          }
        },
      },
      { step: 'auth' }
    );

    if (!authPassed) {
      canaryErrors.add(1, { step: 'auth' });
      fail(`Authentication failed: status=${res.status}`);
    }

    accessToken = JSON.parse(res.body).access_token;
  });

  const authHeaders = {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  };

  // -------------------------------------------------------------------------
  // Step 2: List API Catalog
  // -------------------------------------------------------------------------
  group('2. List API Catalog', () => {
    const res = http.get(`https://api.${BASE_DOMAIN}/v1/catalog/apis?page=1&per_page=5`, {
      headers: authHeaders,
      tags: { step: 'catalog' },
      timeout: '10s',
    });

    stepLatency.add(res.timings.duration, { step: 'catalog' });

    const catalogPassed = check(
      res,
      {
        catalog_200: (r) => r.status === 200,
        catalog_has_items: (r) => {
          try {
            const body = JSON.parse(r.body);
            return Array.isArray(body.items || body.data || body);
          } catch {
            return false;
          }
        },
      },
      { step: 'catalog' }
    );

    if (!catalogPassed) {
      canaryErrors.add(1, { step: 'catalog' });
      console.error(`[FAIL] Catalog list: status=${res.status}`);
    }
  });

  // -------------------------------------------------------------------------
  // Step 3: List MCP Tools
  // -------------------------------------------------------------------------
  group('3. List MCP Tools', () => {
    const res = http.get(`https://mcp.${BASE_DOMAIN}/tools`, {
      headers: authHeaders,
      tags: { step: 'tools' },
      timeout: '10s',
    });

    stepLatency.add(res.timings.duration, { step: 'tools' });

    const toolsPassed = check(
      res,
      {
        tools_200: (r) => r.status === 200,
        tools_has_list: (r) => {
          try {
            const body = JSON.parse(r.body);
            return Array.isArray(body.tools || body);
          } catch {
            return false;
          }
        },
      },
      { step: 'tools' }
    );

    if (!toolsPassed) {
      canaryErrors.add(1, { step: 'tools' });
      console.error(`[FAIL] Tools list: status=${res.status}`);
    }
  });

  // -------------------------------------------------------------------------
  // Step 4: Invoke canary tool
  // -------------------------------------------------------------------------
  group('4. Invoke Canary Tool', () => {
    const payload = JSON.stringify({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'stoa-health-check',
        arguments: { check_type: 'canary' },
      },
      id: `canary-${Date.now()}`,
    });

    const res = http.post(`https://mcp.${BASE_DOMAIN}/mcp/v1`, payload, {
      headers: authHeaders,
      tags: { step: 'invoke' },
      timeout: '15s',
    });

    stepLatency.add(res.timings.duration, { step: 'invoke' });

    const invokePassed = check(
      res,
      {
        invoke_success: (r) => r.status === 200,
        invoke_has_result: (r) => {
          try {
            const body = JSON.parse(r.body);
            return !!body.result || body.error === undefined;
          } catch {
            return false;
          }
        },
      },
      { step: 'invoke' }
    );

    if (!invokePassed) {
      canaryErrors.add(1, { step: 'invoke' });
      console.error(`[FAIL] Tool invoke: status=${res.status}`);
    }
  });
}
