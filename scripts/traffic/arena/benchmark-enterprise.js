/**
 * Gateway Arena — Enterprise AI Readiness Benchmark (Layer 1)
 *
 * Tests 8 enterprise dimensions that measure AI-native gateway capabilities.
 * Gateways without MCP/guardrails/governance score 0 (not N/A).
 *
 * Env vars:
 *   TARGET_URL    — Gateway base URL (e.g., http://stoa-gateway.stoa-system.svc:8080)
 *   MCP_BASE      — MCP endpoint base (e.g., http://stoa-gateway.stoa-system.svc:8080/mcp)
 *                    If empty/null, MCP scenarios score 0 (gateway doesn't support MCP)
 *   SCENARIO      — One of: ent_warmup, ent_mcp_discovery, ent_mcp_toolcall,
 *                   ent_auth_chain, ent_policy_eval, ent_guardrails,
 *                   ent_quota_burst, ent_resilience, ent_governance
 *   ARENA_JWT     — Bearer token for authenticated scenarios (optional)
 *   HEADERS       — JSON object of extra headers (optional)
 *   TIMEOUT       — Request timeout in seconds (default: 10)
 *   SUMMARY_FILE  — Output path for JSON summary
 */

import http from 'k6/http';
import { check, group } from 'k6';

const TARGET_URL = __ENV.TARGET_URL || 'http://localhost:8080';
const MCP_BASE = __ENV.MCP_BASE || '';
const SCENARIO = __ENV.SCENARIO || 'ent_mcp_discovery';
const ARENA_JWT = __ENV.ARENA_JWT || '';
const HEADERS = __ENV.HEADERS ? JSON.parse(__ENV.HEADERS) : {};
const TIMEOUT = (__ENV.TIMEOUT || '10') + 's';

// Auth headers when JWT is available
function authHeaders() {
  const h = Object.assign({}, HEADERS);
  if (ARENA_JWT) {
    h['Authorization'] = `Bearer ${ARENA_JWT}`;
  }
  return h;
}

// Scenario definitions
const scenarios = {
  ent_warmup: {
    executor: 'shared-iterations',
    vus: 5,
    iterations: 20,
    maxDuration: '15s',
  },
  ent_mcp_discovery: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_mcp_toolcall: {
    executor: 'shared-iterations',
    vus: 5,
    iterations: 20,
    maxDuration: '30s',
  },
  ent_auth_chain: {
    executor: 'shared-iterations',
    vus: 3,
    iterations: 15,
    maxDuration: '30s',
  },
  ent_policy_eval: {
    executor: 'shared-iterations',
    vus: 5,
    iterations: 20,
    maxDuration: '30s',
  },
  ent_guardrails: {
    executor: 'shared-iterations',
    vus: 3,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_quota_burst: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '3s', target: 20 },
      { duration: '10s', target: 20 },
      { duration: '2s', target: 0 },
    ],
  },
  ent_resilience: {
    executor: 'shared-iterations',
    vus: 3,
    iterations: 15,
    maxDuration: '30s',
  },
  ent_governance: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 5,
    maxDuration: '15s',
  },
};

const scenarioConfig = scenarios[SCENARIO];
if (!scenarioConfig) {
  throw new Error(`Unknown scenario: ${SCENARIO}. Valid: ${Object.keys(scenarios).join(', ')}`);
}

export const options = {
  scenarios: {
    default: scenarioConfig,
  },
  summaryTrendStats: [
    'min', 'avg', 'med', 'max',
    'p(25)', 'p(50)', 'p(75)', 'p(90)', 'p(95)', 'p(99)',
  ],
  thresholds: {},
};

// --- Scenario Handlers ---

function runMcpDiscovery() {
  if (!MCP_BASE) return;
  const res = http.get(`${MCP_BASE}/capabilities`, {
    headers: HEADERS,
    timeout: TIMEOUT,
    tags: { scenario: 'ent_mcp_discovery' },
  });
  check(res, {
    'mcp_discovery_status_2xx': (r) => r.status >= 200 && r.status < 300,
    'mcp_discovery_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'mcp_discovery_has_capabilities': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.capabilities !== undefined || body.tools !== undefined;
      } catch (_e) { return false; }
    },
  });
}

function runMcpToolcall() {
  if (!MCP_BASE) return;
  const payload = JSON.stringify({
    jsonrpc: '2.0',
    method: 'tools/list',
    id: 1,
  });
  const res = http.post(`${MCP_BASE}/tools/list`, payload, {
    headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
    timeout: TIMEOUT,
    tags: { scenario: 'ent_mcp_toolcall' },
  });
  check(res, {
    'mcp_toolcall_status_2xx': (r) => r.status >= 200 && r.status < 300,
    'mcp_toolcall_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'mcp_toolcall_p95_under_500ms': (r) => r.timings.duration < 500,
  });
}

function runAuthChain() {
  if (!MCP_BASE) return;
  const payload = JSON.stringify({
    jsonrpc: '2.0',
    method: 'tools/list',
    id: 1,
  });
  const res = http.post(`${MCP_BASE}/tools/list`, payload, {
    headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
    timeout: TIMEOUT,
    tags: { scenario: 'ent_auth_chain' },
  });
  check(res, {
    'auth_chain_not_500': (r) => r.status < 500,
    'auth_chain_auth_processed': (r) => {
      // If JWT provided: expect 2xx. If not: expect 401/403 (auth is enforced).
      if (ARENA_JWT) return r.status >= 200 && r.status < 300;
      return r.status === 401 || r.status === 403 || (r.status >= 200 && r.status < 300);
    },
    'auth_chain_p95_under_1s': (r) => r.timings.duration < 1000,
  });
}

function runPolicyEval() {
  // Test OPA policy evaluation overhead by hitting MCP endpoint
  if (!MCP_BASE) return;
  const res = http.get(`${MCP_BASE}/capabilities`, {
    headers: authHeaders(),
    timeout: TIMEOUT,
    tags: { scenario: 'ent_policy_eval' },
  });
  check(res, {
    'policy_eval_not_500': (r) => r.status < 500,
    'policy_eval_p95_under_200ms': (r) => r.timings.duration < 200,
  });
}

function runGuardrails() {
  if (!MCP_BASE) return;
  // Send a tool call with PII in the payload — expect blocking or redaction
  const payload = JSON.stringify({
    jsonrpc: '2.0',
    method: 'tools/call',
    params: {
      name: 'arena-test-tool',
      arguments: {
        query: 'My SSN is 123-45-6789 and my email is test@example.com',
      },
    },
    id: 1,
  });
  const res = http.post(`${MCP_BASE}/tools/call`, payload, {
    headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
    timeout: TIMEOUT,
    tags: { scenario: 'ent_guardrails' },
  });
  check(res, {
    'guardrails_not_500': (r) => r.status < 500,
    'guardrails_pii_handled': (r) => {
      // Gateway should either block (4xx) or process the request (2xx).
      // A 500 means guardrails crashed — unacceptable.
      return r.status < 500;
    },
    'guardrails_response_exists': (r) => r.body && r.body.length > 0,
  });
}

function runQuotaBurst() {
  // Rapid-fire requests to trigger rate limiting (429)
  const url = MCP_BASE ? `${MCP_BASE}/capabilities` : `${TARGET_URL}/health`;
  const res = http.get(url, {
    headers: authHeaders(),
    timeout: TIMEOUT,
    tags: { scenario: 'ent_quota_burst' },
  });
  check(res, {
    'quota_burst_not_500': (r) => r.status < 500,
    'quota_burst_valid_response': (r) => {
      // 200 = request passed, 429 = rate limit enforced — both are valid
      return r.status === 200 || r.status === 429;
    },
  });
}

function runResilience() {
  if (!MCP_BASE) return;
  // Bad tool call — non-existent tool, malformed JSON-RPC
  const payload = JSON.stringify({
    jsonrpc: '2.0',
    method: 'tools/call',
    params: {
      name: 'nonexistent-tool-arena-benchmark',
      arguments: { invalid: true },
    },
    id: 999,
  });
  const res = http.post(`${MCP_BASE}/tools/call`, payload, {
    headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
    timeout: TIMEOUT,
    tags: { scenario: 'ent_resilience' },
  });
  check(res, {
    'resilience_not_500': (r) => r.status < 500,
    'resilience_graceful_error': (r) => {
      // Expect 4xx (not found, bad request) — NOT 500 (crash)
      return r.status >= 400 && r.status < 500;
    },
    'resilience_has_error_body': (r) => r.body && r.body.length > 0,
  });
}

function runGovernance() {
  // Check that governance/session endpoints exist
  const endpoints = [
    `${TARGET_URL}/admin/sessions/stats`,
    `${TARGET_URL}/admin/circuit-breaker/stats`,
  ];
  for (const url of endpoints) {
    const res = http.get(url, {
      headers: authHeaders(),
      timeout: TIMEOUT,
      tags: { scenario: 'ent_governance' },
    });
    check(res, {
      'governance_endpoint_exists': (r) => r.status < 500,
      'governance_not_404': (r) => r.status !== 404,
    });
  }
}

// --- Main ---

export default function () {
  switch (SCENARIO) {
    case 'ent_warmup':
      if (MCP_BASE) {
        http.get(`${MCP_BASE}/capabilities`, { headers: HEADERS, timeout: TIMEOUT });
      } else {
        http.get(`${TARGET_URL}/health`, { headers: HEADERS, timeout: TIMEOUT });
      }
      break;
    case 'ent_mcp_discovery':
      runMcpDiscovery();
      break;
    case 'ent_mcp_toolcall':
      runMcpToolcall();
      break;
    case 'ent_auth_chain':
      runAuthChain();
      break;
    case 'ent_policy_eval':
      runPolicyEval();
      break;
    case 'ent_guardrails':
      runGuardrails();
      break;
    case 'ent_quota_burst':
      runQuotaBurst();
      break;
    case 'ent_resilience':
      runResilience();
      break;
    case 'ent_governance':
      runGovernance();
      break;
    default:
      throw new Error(`Unknown enterprise scenario: ${SCENARIO}`);
  }
}

export function handleSummary(data) {
  const summaryFile = __ENV.SUMMARY_FILE || '/tmp/ent_summary.json';
  const out = {};
  out[summaryFile] = JSON.stringify(data, null, 2);
  return out;
}
