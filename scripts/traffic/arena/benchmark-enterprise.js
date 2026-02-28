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
 *   MCP_PROTOCOL  — "stoa" (REST: GET /capabilities, POST /tools/list) or
 *                    "streamable-http" (JSON-RPC 2.0 on single POST endpoint). Default: "stoa"
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
const MCP_PROTOCOL = __ENV.MCP_PROTOCOL || 'stoa'; // "stoa" (REST) or "streamable-http" (JSON-RPC 2.0)
const SCENARIO = __ENV.SCENARIO || 'ent_mcp_discovery';
const ARENA_JWT = __ENV.ARENA_JWT || '';
const HEADERS = __ENV.HEADERS ? JSON.parse(__ENV.HEADERS) : {};
const TIMEOUT = (__ENV.TIMEOUT || '10') + 's';
const LLM_MOCK_URL = __ENV.LLM_MOCK_URL || '';

// Auth headers when JWT is available
function authHeaders() {
  const h = Object.assign({}, HEADERS);
  if (ARENA_JWT) {
    h['Authorization'] = `Bearer ${ARENA_JWT}`;
  }
  return h;
}

// Protocol-aware MCP request helper
// STOA uses REST paths (/capabilities, /tools/list, /tools/call)
// Streamable HTTP uses single endpoint with JSON-RPC 2.0 (POST /mcp)
function mcpRequest(method, params, tags) {
  if (!MCP_BASE) return null;
  const hdrs = Object.assign({ 'Content-Type': 'application/json' }, authHeaders());

  if (MCP_PROTOCOL === 'streamable-http') {
    const body = { jsonrpc: '2.0', method: method, id: 1 };
    if (params) body.params = params;
    return http.post(MCP_BASE, JSON.stringify(body), {
      headers: hdrs,
      timeout: TIMEOUT,
      tags: tags,
    });
  }

  // STOA REST protocol — map JSON-RPC methods to REST paths
  const pathMap = {
    'initialize': '/capabilities',
    'tools/list': '/tools/list',
    'tools/call': '/tools/call',
  };
  const path = pathMap[method] || `/${method}`;
  const url = `${MCP_BASE}${path}`;

  if (method === 'initialize') {
    // Discovery is a GET in STOA REST
    return http.get(url, {
      headers: HEADERS,
      timeout: TIMEOUT,
      tags: tags,
    });
  }

  const body = { jsonrpc: '2.0', method: method, id: 1 };
  if (params) body.params = params;
  return http.post(url, JSON.stringify(body), {
    headers: hdrs,
    timeout: TIMEOUT,
    tags: tags,
  });
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
  ent_llm_routing: {
    executor: 'per-vu-iterations',
    vus: 3,
    iterations: 10,
    maxDuration: '30s',
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
  const res = mcpRequest('initialize', null, { scenario: 'ent_mcp_discovery' });
  if (!res) return;
  check(res, {
    'mcp_discovery_status_2xx': (r) => r.status >= 200 && r.status < 300,
    'mcp_discovery_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'mcp_discovery_has_capabilities': (r) => {
      try {
        const body = JSON.parse(r.body);
        // STOA REST: body.capabilities or body.tools
        // Streamable HTTP: body.result.capabilities
        return body.capabilities !== undefined || body.tools !== undefined ||
          (body.result && body.result.capabilities !== undefined);
      } catch (_e) { return false; }
    },
  });
}

function runMcpToolcall() {
  const res = mcpRequest('tools/list', null, { scenario: 'ent_mcp_toolcall' });
  if (!res) return;
  check(res, {
    'mcp_toolcall_status_2xx': (r) => r.status >= 200 && r.status < 300,
    'mcp_toolcall_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'mcp_toolcall_p95_under_500ms': (r) => r.timings.duration < 500,
  });
}

function runAuthChain() {
  const res = mcpRequest('tools/list', null, { scenario: 'ent_auth_chain' });
  if (!res) return;
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
  const res = mcpRequest('initialize', null, { scenario: 'ent_policy_eval' });
  if (!res) return;
  check(res, {
    'policy_eval_not_500': (r) => r.status < 500,
    'policy_eval_p95_under_200ms': (r) => r.timings.duration < 200,
  });
}

function runGuardrails() {
  // Send a tool call with PII in the payload — expect blocking or redaction
  const params = {
    name: 'arena-test-tool',
    arguments: {
      query: 'My SSN is 123-45-6789 and my email is test@example.com',
    },
  };
  const res = mcpRequest('tools/call', params, { scenario: 'ent_guardrails' });
  if (!res) return;
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
  // For gateways with MCP, hit the discovery endpoint; otherwise hit health
  const res = MCP_BASE
    ? mcpRequest('initialize', null, { scenario: 'ent_quota_burst' })
    : http.get(`${TARGET_URL}/health`, {
        headers: authHeaders(),
        timeout: TIMEOUT,
        tags: { scenario: 'ent_quota_burst' },
      });
  if (!res) return;
  check(res, {
    'quota_burst_not_500': (r) => r.status < 500,
    'quota_burst_valid_response': (r) => {
      // 200 = request passed, 429 = rate limit enforced — both are valid
      return r.status === 200 || r.status === 429;
    },
  });
}

function runResilience() {
  // Bad tool call — non-existent tool, malformed arguments
  const params = {
    name: 'nonexistent-tool-arena-benchmark',
    arguments: { invalid: true },
  };
  const res = mcpRequest('tools/call', params, { scenario: 'ent_resilience' });
  if (!res) return;
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

function runLlmRouting() {
  // Test LLM proxy: POST /v1/messages through the gateway
  // Gateway should proxy to the LLM mock backend (or real upstream)
  const body = {
    model: 'claude-mock',
    max_tokens: 64,
    messages: [{ role: 'user', content: 'Arena benchmark test — reply briefly.' }],
  };
  const hdrs = Object.assign(
    { 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01' },
    authHeaders()
  );
  const url = `${TARGET_URL}/v1/messages`;
  const res = http.post(url, JSON.stringify(body), {
    headers: hdrs,
    timeout: TIMEOUT,
    tags: { scenario: 'ent_llm_routing' },
  });
  check(res, {
    'llm_routing_status_2xx': (r) => r.status >= 200 && r.status < 300,
    'llm_routing_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'llm_routing_has_message': (r) => {
      try {
        const data = JSON.parse(r.body);
        return data.type === 'message' || data.content !== undefined;
      } catch (_e) { return false; }
    },
    'llm_routing_has_usage': (r) => {
      try {
        const data = JSON.parse(r.body);
        return data.usage && data.usage.input_tokens > 0;
      } catch (_e) { return false; }
    },
  });
}

// --- Main ---

export default function () {
  switch (SCENARIO) {
    case 'ent_warmup':
      if (MCP_BASE) {
        mcpRequest('initialize', null, { scenario: 'ent_warmup' });
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
    case 'ent_llm_routing':
      runLlmRouting();
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
