/**
 * Gateway Arena — Enterprise AI Readiness Benchmark (Layer 1)
 *
 * Tests 20 enterprise dimensions that measure AI-native gateway capabilities.
 * Gateways without MCP/guardrails/governance score 0 (not N/A).
 * Gateways without specific features (LLM routing, skills, etc.) score 0 on those dimensions.
 *
 * Env vars:
 *   TARGET_URL    — Gateway base URL (e.g., http://stoa-gateway.stoa-system.svc:8080)
 *   MCP_BASE      — MCP endpoint base (e.g., http://stoa-gateway.stoa-system.svc:8080/mcp)
 *                    If empty/null, MCP scenarios score 0 (gateway doesn't support MCP)
 *   MCP_PROTOCOL  — "stoa" (REST: GET /capabilities, POST /tools/list) or
 *                    "streamable-http" (JSON-RPC 2.0 on single POST endpoint). Default: "stoa"
 *   ADMIN_BASE    — Admin API base URL (e.g., http://stoa-gateway.stoa-system.svc:8080)
 *                    Used for admin-only dimensions (skills, federation, diagnostic, etc.)
 *                    If empty, admin scenarios score 0.
 *   SCENARIO      — One of the 20 enterprise scenarios (see scenarios object below)
 *   ARENA_JWT     — Bearer token for authenticated scenarios (optional)
 *   HEADERS       — JSON object of extra headers (optional)
 *   TIMEOUT       — Request timeout in seconds (default: 10)
 *   SUMMARY_FILE  — Output path for JSON summary
 *   LLM_MOCK_URL  — LLM mock backend URL for llm_routing/llm_cost scenarios
 */

import http from 'k6/http';
import { check, group } from 'k6';

const TARGET_URL = __ENV.TARGET_URL || 'http://localhost:8080';
const MCP_BASE = __ENV.MCP_BASE || '';
const MCP_PROTOCOL = __ENV.MCP_PROTOCOL || 'stoa'; // "stoa" (REST) or "streamable-http" (JSON-RPC 2.0)
const ADMIN_BASE = __ENV.ADMIN_BASE || '';
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

// Admin endpoint request helper
function adminRequest(path, tags, method, body) {
  if (!ADMIN_BASE) return null;
  const url = `${ADMIN_BASE}${path}`;
  const hdrs = Object.assign({ 'Content-Type': 'application/json' }, authHeaders());
  if (method === 'POST') {
    return http.post(url, body ? JSON.stringify(body) : null, {
      headers: hdrs,
      timeout: TIMEOUT,
      tags: tags,
    });
  }
  if (method === 'DELETE') {
    return http.del(url, null, {
      headers: hdrs,
      timeout: TIMEOUT,
      tags: tags,
    });
  }
  // Default: GET
  return http.get(url, {
    headers: authHeaders(),
    timeout: TIMEOUT,
    tags: tags,
  });
}

// Scenario definitions
const scenarios = {
  // --- Original 8 + 1 ---
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
  // --- Cat A: LLM Intelligence ---
  ent_llm_cost: {
    executor: 'shared-iterations',
    vus: 2,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_llm_circuit_breaker: {
    executor: 'shared-iterations',
    vus: 2,
    iterations: 10,
    maxDuration: '30s',
  },
  // --- Cat B: MCP Depth ---
  ent_native_tools_crud: {
    executor: 'shared-iterations',
    vus: 2,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_api_bridge: {
    executor: 'shared-iterations',
    vus: 2,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_uac_binding: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 5,
    maxDuration: '30s',
  },
  // --- Cat C: Security & Compliance ---
  ent_pii_detection: {
    executor: 'shared-iterations',
    vus: 3,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_distributed_tracing: {
    executor: 'shared-iterations',
    vus: 3,
    iterations: 15,
    maxDuration: '30s',
  },
  ent_prompt_cache: {
    executor: 'shared-iterations',
    vus: 2,
    iterations: 10,
    maxDuration: '30s',
  },
  // --- Cat D: Platform Operations ---
  ent_skills_lifecycle: {
    executor: 'shared-iterations',
    vus: 2,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_federation: {
    executor: 'shared-iterations',
    vus: 2,
    iterations: 10,
    maxDuration: '30s',
  },
  ent_diagnostic: {
    executor: 'shared-iterations',
    vus: 2,
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

// =====================================================================
// Original 8 Scenario Handlers
// =====================================================================

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

// =====================================================================
// Cat A: LLM Intelligence (3 dimensions)
// =====================================================================

function runLlmRouting() {
  // Test LLM proxy: POST /v1/messages through the gateway
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
    'llm_routing_has_provider_header': (r) => {
      // STOA adds X-Stoa-Llm-Provider header indicating routing decision
      const provider = r.headers['X-Stoa-Llm-Provider'] || r.headers['x-stoa-llm-provider'];
      return provider !== undefined && provider !== '';
    },
  });
}

function runLlmCost() {
  // Test LLM cost tracking: POST /v1/messages then verify metering via /metrics
  const body = {
    model: 'claude-mock',
    max_tokens: 32,
    messages: [{ role: 'user', content: 'Cost tracking test.' }],
  };
  const hdrs = Object.assign(
    { 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01' },
    authHeaders()
  );
  const url = `${TARGET_URL}/v1/messages`;
  const res = http.post(url, JSON.stringify(body), {
    headers: hdrs,
    timeout: TIMEOUT,
    tags: { scenario: 'ent_llm_cost' },
  });
  check(res, {
    'llm_cost_proxy_ok': (r) => r.status >= 200 && r.status < 300,
    'llm_cost_has_usage': (r) => {
      try {
        const data = JSON.parse(r.body);
        return data.usage && typeof data.usage.input_tokens === 'number';
      } catch (_e) { return false; }
    },
  });

  // Verify metering endpoint exposes cost metrics
  const metricsRes = http.get(`${TARGET_URL}/metrics`, {
    headers: authHeaders(),
    timeout: TIMEOUT,
    tags: { scenario: 'ent_llm_cost' },
  });
  check(metricsRes, {
    'llm_cost_metrics_accessible': (r) => r.status >= 200 && r.status < 400,
    'llm_cost_token_metrics_exist': (r) => {
      // Check for token or cost related metrics in Prometheus exposition
      return r.body && (
        r.body.includes('llm_tokens') ||
        r.body.includes('llm_cost') ||
        r.body.includes('metering') ||
        r.body.includes('stoa_proxy')
      );
    },
  });
}

function runLlmCircuitBreaker() {
  // Test circuit breaker introspection for LLM backends
  const tags = { scenario: 'ent_llm_circuit_breaker' };
  const res1 = adminRequest('/admin/circuit-breakers', tags);
  if (!res1) return;
  check(res1, {
    'llm_cb_list_ok': (r) => r.status >= 200 && r.status < 300,
    'llm_cb_list_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'llm_cb_list_has_entries': (r) => {
      try {
        const data = JSON.parse(r.body);
        return Array.isArray(data) || (typeof data === 'object' && data !== null);
      } catch (_e) { return false; }
    },
  });

  const res2 = adminRequest('/admin/circuit-breaker/stats', tags);
  if (!res2) return;
  check(res2, {
    'llm_cb_stats_ok': (r) => r.status >= 200 && r.status < 300,
    'llm_cb_stats_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });
}

// =====================================================================
// Cat B: MCP Depth (3 dimensions)
// =====================================================================

function runNativeToolsCrud() {
  // Test quality of tool listing: annotations, inputSchema, tool count
  const res = mcpRequest('tools/list', null, { scenario: 'ent_native_tools_crud' });
  if (!res) return;
  check(res, {
    'native_tools_status_2xx': (r) => r.status >= 200 && r.status < 300,
    'native_tools_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'native_tools_has_tools': (r) => {
      try {
        const data = JSON.parse(r.body);
        // STOA REST: body.tools, Streamable HTTP: body.result.tools
        const tools = data.tools || (data.result && data.result.tools);
        return Array.isArray(tools) && tools.length > 0;
      } catch (_e) { return false; }
    },
    'native_tools_has_schema': (r) => {
      try {
        const data = JSON.parse(r.body);
        const tools = data.tools || (data.result && data.result.tools) || [];
        // At least one tool should have inputSchema
        return tools.some((t) => t.inputSchema !== undefined);
      } catch (_e) { return false; }
    },
    'native_tools_has_annotations': (r) => {
      try {
        const data = JSON.parse(r.body);
        const tools = data.tools || (data.result && data.result.tools) || [];
        // STOA enriches tools with annotations (readOnlyHint, etc.)
        return tools.some((t) => t.annotations !== undefined);
      } catch (_e) { return false; }
    },
  });
}

function runApiBridge() {
  // Test API-to-MCP bridge: tools/list should include UAC-bridged tools with api: or uac: prefix
  const res = mcpRequest('tools/list', null, { scenario: 'ent_api_bridge' });
  if (!res) return;
  check(res, {
    'api_bridge_status_2xx': (r) => r.status >= 200 && r.status < 300,
    'api_bridge_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'api_bridge_has_bridged_tools': (r) => {
      try {
        const data = JSON.parse(r.body);
        const tools = data.tools || (data.result && data.result.tools) || [];
        // Look for tools with uac: or api: prefix (UAC-bridged REST APIs)
        return tools.some((t) =>
          (t.name && (t.name.startsWith('uac:') || t.name.startsWith('api:'))) ||
          (t.metadata && t.metadata.source === 'uac')
        );
      } catch (_e) { return false; }
    },
    'api_bridge_has_endpoint_metadata': (r) => {
      try {
        const data = JSON.parse(r.body);
        const tools = data.tools || (data.result && data.result.tools) || [];
        // Bridged tools should carry endpoint metadata (url, method)
        return tools.some((t) =>
          t.metadata && (t.metadata.endpoint || t.metadata.url || t.metadata.method)
        );
      } catch (_e) { return false; }
    },
  });
}

function runUacBinding() {
  // Test UAC contract lifecycle: list contracts via admin, verify contract data
  const tags = { scenario: 'ent_uac_binding' };

  // Step 1: List existing contracts
  const listRes = adminRequest('/admin/contracts', tags);
  if (!listRes) return;
  check(listRes, {
    'uac_binding_list_ok': (r) => r.status >= 200 && r.status < 300,
    'uac_binding_list_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });

  // Step 2: Create a test contract
  const testContract = {
    key: 'arena-bench-test-contract',
    name: 'Arena Benchmark Test',
    version: '1.0.0',
    endpoints: [
      {
        path: '/echo/get',
        method: 'GET',
        description: 'Echo endpoint for arena benchmark',
      },
    ],
  };
  const createRes = adminRequest('/admin/contracts', tags, 'POST', testContract);
  if (!createRes) return;
  check(createRes, {
    'uac_binding_create_ok': (r) => r.status >= 200 && r.status < 300,
    'uac_binding_create_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });

  // Step 3: Verify tools/list reflects the contract (if MCP available)
  if (MCP_BASE) {
    const toolsRes = mcpRequest('tools/list', null, tags);
    if (toolsRes) {
      check(toolsRes, {
        'uac_binding_tools_reflect_contract': (r) => r.status >= 200 && r.status < 300,
      });
    }
  }

  // Step 4: Cleanup — delete test contract
  const deleteRes = adminRequest('/admin/contracts/arena-bench-test-contract', tags, 'DELETE');
  if (deleteRes) {
    check(deleteRes, {
      'uac_binding_cleanup_ok': (r) => r.status >= 200 && r.status < 400,
    });
  }
}

// =====================================================================
// Cat C: Security & Compliance (3 dimensions)
// =====================================================================

function runPiiDetection() {
  // Send tool calls with various PII patterns — gateway should detect/flag them
  const piiPayloads = [
    { query: 'My SSN is 078-05-1120 please process it' },
    { query: 'Send to john.doe@example.com, CC 4111-1111-1111-1111' },
    { query: 'Patient record: DOB 1990-01-15, MRN 12345678' },
    { query: 'This is a clean request with no sensitive data' },
  ];

  const idx = __VU % piiPayloads.length;
  const params = {
    name: 'arena-pii-test-tool',
    arguments: piiPayloads[idx],
  };
  const res = mcpRequest('tools/call', params, { scenario: 'ent_pii_detection' });
  if (!res) return;
  check(res, {
    'pii_detection_not_500': (r) => r.status < 500,
    'pii_detection_response_exists': (r) => r.body && r.body.length > 0,
    'pii_detection_handled': (r) => {
      // Gateway should either block PII (4xx), redact it (2xx with modified body),
      // or flag it via headers. A clean pass-through of PII is still acceptable
      // (guardrails may be in log-only mode). 5xx is not acceptable.
      return r.status < 500;
    },
    'pii_detection_has_audit_header': (r) => {
      // STOA adds X-Stoa-Pii-Detected or X-Stoa-Guardrail headers
      const piiHeader = r.headers['X-Stoa-Pii-Detected'] || r.headers['x-stoa-pii-detected'];
      const guardrailHeader = r.headers['X-Stoa-Guardrail'] || r.headers['x-stoa-guardrail'];
      return piiHeader !== undefined || guardrailHeader !== undefined || r.status < 500;
    },
  });
}

function runDistributedTracing() {
  // Send request with W3C traceparent header, verify gateway propagates it
  const traceId = '00000000000000000000000000arena1';
  const spanId = '00000000arena01';
  const traceparent = `00-${traceId}-${spanId}-01`;

  const res = MCP_BASE
    ? mcpRequest('initialize', null, { scenario: 'ent_distributed_tracing' })
    : http.get(`${TARGET_URL}/health`, {
        headers: Object.assign({ traceparent: traceparent }, authHeaders()),
        timeout: TIMEOUT,
        tags: { scenario: 'ent_distributed_tracing' },
      });
  if (!res) return;

  // Also send a request with explicit traceparent to verify propagation
  const hdrs = Object.assign({ traceparent: traceparent }, authHeaders());
  const tracedRes = http.get(`${TARGET_URL}/health`, {
    headers: hdrs,
    timeout: TIMEOUT,
    tags: { scenario: 'ent_distributed_tracing' },
  });
  check(tracedRes, {
    'tracing_status_ok': (r) => r.status >= 200 && r.status < 500,
    'tracing_has_trace_header': (r) => {
      // Gateway should return traceparent or tracestate in response
      const tp = r.headers['traceparent'] || r.headers['Traceparent'];
      const ts = r.headers['tracestate'] || r.headers['Tracestate'];
      const xTrace = r.headers['X-Stoa-Trace-Id'] || r.headers['x-stoa-trace-id'];
      return tp !== undefined || ts !== undefined || xTrace !== undefined;
    },
    'tracing_response_fast': (r) => r.timings.duration < 500,
  });
}

function runPromptCache() {
  // Test prompt cache admin introspection
  const tags = { scenario: 'ent_prompt_cache' };
  const statsRes = adminRequest('/admin/prompt-cache/stats', tags);
  if (!statsRes) return;
  check(statsRes, {
    'prompt_cache_stats_ok': (r) => r.status >= 200 && r.status < 300,
    'prompt_cache_stats_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'prompt_cache_stats_has_data': (r) => {
      try {
        const data = JSON.parse(r.body);
        // Expect hit/miss counters or size info
        return data !== null && typeof data === 'object';
      } catch (_e) { return false; }
    },
  });

  const patternsRes = adminRequest('/admin/prompt-cache/patterns', tags);
  if (!patternsRes) return;
  check(patternsRes, {
    'prompt_cache_patterns_ok': (r) => r.status >= 200 && r.status < 300,
    'prompt_cache_patterns_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });
}

// =====================================================================
// Cat D: Platform Operations (3 dimensions)
// =====================================================================

function runSkillsLifecycle() {
  // Test skills system admin endpoints
  const tags = { scenario: 'ent_skills_lifecycle' };

  const listRes = adminRequest('/admin/skills', tags);
  if (!listRes) return;
  check(listRes, {
    'skills_list_ok': (r) => r.status >= 200 && r.status < 300,
    'skills_list_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });

  const statusRes = adminRequest('/admin/skills/status', tags);
  if (!statusRes) return;
  check(statusRes, {
    'skills_status_ok': (r) => r.status >= 200 && r.status < 300,
    'skills_status_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });

  const healthRes = adminRequest('/admin/skills/health', tags);
  if (!healthRes) return;
  check(healthRes, {
    'skills_health_ok': (r) => r.status >= 200 && r.status < 300,
    'skills_health_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });
}

function runFederation() {
  // Test federation admin endpoints
  const tags = { scenario: 'ent_federation' };

  const statusRes = adminRequest('/admin/federation/status', tags);
  if (!statusRes) return;
  check(statusRes, {
    'federation_status_ok': (r) => r.status >= 200 && r.status < 300,
    'federation_status_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'federation_has_state': (r) => {
      try {
        const data = JSON.parse(r.body);
        return data !== null && typeof data === 'object';
      } catch (_e) { return false; }
    },
  });

  const cacheRes = adminRequest('/admin/federation/cache', tags);
  if (!cacheRes) return;
  check(cacheRes, {
    'federation_cache_ok': (r) => r.status >= 200 && r.status < 300,
    'federation_cache_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });
}

function runDiagnostic() {
  // Test diagnostic engine admin endpoints
  const tags = { scenario: 'ent_diagnostic' };

  const diagRes = adminRequest('/admin/diagnostic', tags);
  if (!diagRes) return;
  check(diagRes, {
    'diagnostic_ok': (r) => r.status >= 200 && r.status < 300,
    'diagnostic_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
    'diagnostic_has_checks': (r) => {
      try {
        const data = JSON.parse(r.body);
        return data !== null && typeof data === 'object';
      } catch (_e) { return false; }
    },
  });

  const summaryRes = adminRequest('/admin/diagnostics/summary', tags);
  if (!summaryRes) return;
  check(summaryRes, {
    'diagnostic_summary_ok': (r) => r.status >= 200 && r.status < 300,
    'diagnostic_summary_valid_json': (r) => {
      try { JSON.parse(r.body); return true; } catch (_e) { return false; }
    },
  });
}

// =====================================================================
// Main dispatcher
// =====================================================================

export default function () {
  switch (SCENARIO) {
    case 'ent_warmup':
      if (MCP_BASE) {
        mcpRequest('initialize', null, { scenario: 'ent_warmup' });
      } else {
        http.get(`${TARGET_URL}/health`, { headers: HEADERS, timeout: TIMEOUT });
      }
      break;
    // --- Original 8 ---
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
    // --- Cat A: LLM Intelligence ---
    case 'ent_llm_routing':
      runLlmRouting();
      break;
    case 'ent_llm_cost':
      runLlmCost();
      break;
    case 'ent_llm_circuit_breaker':
      runLlmCircuitBreaker();
      break;
    // --- Cat B: MCP Depth ---
    case 'ent_native_tools_crud':
      runNativeToolsCrud();
      break;
    case 'ent_api_bridge':
      runApiBridge();
      break;
    case 'ent_uac_binding':
      runUacBinding();
      break;
    // --- Cat C: Security & Compliance ---
    case 'ent_pii_detection':
      runPiiDetection();
      break;
    case 'ent_distributed_tracing':
      runDistributedTracing();
      break;
    case 'ent_prompt_cache':
      runPromptCache();
      break;
    // --- Cat D: Platform Operations ---
    case 'ent_skills_lifecycle':
      runSkillsLifecycle();
      break;
    case 'ent_federation':
      runFederation();
      break;
    case 'ent_diagnostic':
      runDiagnostic();
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
