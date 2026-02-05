// =============================================================================
// STOA Platform - Synthetic Uptime Check
// =============================================================================
// k6 script: Health check all public STOA endpoints
// Schedule: Every 5 minutes via k6-operator CronJob
//
// Endpoints checked:
//   - Control Plane API  /health
//   - MCP Gateway        /health
//   - Developer Portal   / (200 OK)
//   - Console UI         / (200 OK)
//   - Keycloak           /realms/stoa/.well-known/openid-configuration
//
// Metrics exported to Prometheus via remote write:
//   - k6_http_req_duration (histogram)
//   - k6_checks (pass/fail counters)
//   - k6_http_reqs (request count)
// =============================================================================

import http from 'k6/http';
import { check, group } from 'k6';
import { Counter, Trend } from 'k6/metrics';

// Custom metrics for STOA-specific monitoring
const uptimeErrors = new Counter('stoa_synthetic_uptime_errors');
const endpointLatency = new Trend('stoa_synthetic_endpoint_latency', true);

const BASE_DOMAIN = __ENV.BASE_DOMAIN || 'gostoa.dev';

export const options = {
  scenarios: {
    uptime: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 1,
      maxDuration: '30s',
    },
  },
  thresholds: {
    'checks{endpoint:api}': ['rate>0.99'],
    'checks{endpoint:mcp}': ['rate>0.99'],
    'checks{endpoint:portal}': ['rate>0.99'],
    'checks{endpoint:console}': ['rate>0.99'],
    'checks{endpoint:auth}': ['rate>0.99'],
    http_req_duration: ['p(95)<5000'],
  },
  tags: {
    testType: 'uptime',
    platform: 'stoa',
  },
};

const endpoints = [
  {
    name: 'api',
    url: `https://api.${BASE_DOMAIN}/health`,
    expectedStatus: 200,
    checkBody: (body) => {
      try {
        const json = JSON.parse(body);
        return json.status === 'ok' || json.status === 'healthy';
      } catch {
        return false;
      }
    },
  },
  {
    name: 'mcp',
    url: `https://mcp.${BASE_DOMAIN}/health`,
    expectedStatus: 200,
    checkBody: (body) => {
      try {
        const json = JSON.parse(body);
        return json.status === 'ok' || json.status === 'healthy';
      } catch {
        return false;
      }
    },
  },
  {
    name: 'portal',
    url: `https://portal.${BASE_DOMAIN}`,
    expectedStatus: 200,
    checkBody: null,
  },
  {
    name: 'console',
    url: `https://console.${BASE_DOMAIN}`,
    expectedStatus: 200,
    checkBody: null,
  },
  {
    name: 'auth',
    url: `https://auth.${BASE_DOMAIN}/realms/stoa/.well-known/openid-configuration`,
    expectedStatus: 200,
    checkBody: (body) => {
      try {
        const json = JSON.parse(body);
        return !!json.issuer && !!json.token_endpoint;
      } catch {
        return false;
      }
    },
  },
];

export default function () {
  for (const endpoint of endpoints) {
    group(`Check ${endpoint.name}`, () => {
      const res = http.get(endpoint.url, {
        timeout: '10s',
        tags: { endpoint: endpoint.name },
      });

      endpointLatency.add(res.timings.duration, { endpoint: endpoint.name });

      const checks = {
        status_ok: res.status === endpoint.expectedStatus,
        response_time: res.timings.duration < 5000,
      };

      if (endpoint.checkBody) {
        checks.body_valid = endpoint.checkBody(res.body);
      }

      const passed = check(res, checks, { endpoint: endpoint.name });

      if (!passed) {
        uptimeErrors.add(1, { endpoint: endpoint.name });
        console.error(
          `[FAIL] ${endpoint.name}: status=${res.status} duration=${res.timings.duration}ms`
        );
      }
    });
  }
}
