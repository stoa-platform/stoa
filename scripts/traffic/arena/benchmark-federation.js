/**
 * Federation Latency Benchmark — k6 Script (CAB-1936 Phase 1)
 *
 * Measures federated MCP tool call latency through the STOA gateway.
 * Purpose: establish baseline p50/p95/p99 for federation calls to inform
 * whether session pooling is needed (IBM Context Forge claims 10-20x gain).
 *
 * Scenarios:
 *   1. discovery   — GET /mcp/tools/list (tool catalog fetch)
 *   2. tool_call   — POST /mcp/tools/call (single tool invocation)
 *   3. burst_calls — 10 concurrent tool calls (simulates agent batch)
 *   4. sequential  — 50 sequential tool calls (simulates conversation)
 *
 * Env vars:
 *   GATEWAY_URL  — STOA gateway base URL (default: http://localhost:8080)
 *   AUTH_TOKEN   — Bearer token for authentication (optional)
 *   TOOL_NAME    — MCP tool name to invoke (default: echo)
 *   SCENARIO     — One of: discovery, tool_call, burst_calls, sequential
 *   TIMEOUT      — Request timeout in seconds (default: 10)
 *
 * Usage:
 *   # Single scenario
 *   k6 run -e GATEWAY_URL=https://mcp.gostoa.dev -e SCENARIO=discovery benchmark-federation.js
 *
 *   # All scenarios (via orchestrator)
 *   ./run-federation-bench.sh --gateway https://mcp.gostoa.dev --output results/
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';

// --- Configuration ---

const GATEWAY_URL = __ENV.GATEWAY_URL || 'http://localhost:8080';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';
const TOOL_NAME = __ENV.TOOL_NAME || 'echo';
const SCENARIO = __ENV.SCENARIO || 'discovery';
const TIMEOUT = (__ENV.TIMEOUT || '10') + 's';

// --- Custom Metrics ---

const federationLatency = new Trend('federation_latency_ms', true);
const federationErrors = new Counter('federation_errors');
const federationSuccess = new Rate('federation_success_rate');

// --- Scenario Definitions ---

const scenarios = {
  discovery: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 50,
    maxDuration: '30s',
  },
  tool_call: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 50,
    maxDuration: '60s',
  },
  burst_calls: {
    executor: 'shared-iterations',
    vus: 10,
    iterations: 100,
    maxDuration: '30s',
  },
  sequential: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 50,
    maxDuration: '120s',
  },
};

export const options = {
  scenarios: {
    default: scenarios[SCENARIO] || scenarios.discovery,
  },
  thresholds: {
    federation_latency_ms: [
      'p(50)<100',   // p50 under 100ms
      'p(95)<500',   // p95 under 500ms
      'p(99)<1000',  // p99 under 1s
    ],
    federation_success_rate: ['rate>0.95'],
  },
};

// --- Helpers ---

function headers() {
  const h = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (AUTH_TOKEN) {
    h['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }
  return h;
}

function jsonRpcRequest(method, params) {
  return JSON.stringify({
    jsonrpc: '2.0',
    id: `bench-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    method: method,
    params: params || {},
  });
}

function recordResult(res, label) {
  const success = res.status >= 200 && res.status < 300;
  federationLatency.add(res.timings.duration);
  federationSuccess.add(success);
  if (!success) {
    federationErrors.add(1);
  }

  check(res, {
    [`${label}: status 2xx`]: (r) => r.status >= 200 && r.status < 300,
    [`${label}: latency < 500ms`]: (r) => r.timings.duration < 500,
    [`${label}: valid JSON response`]: (r) => {
      try { JSON.parse(r.body); return true; } catch { return false; }
    },
  });
}

// --- Scenarios ---

function runDiscovery() {
  const res = http.post(
    `${GATEWAY_URL}/mcp/tools/list`,
    jsonRpcRequest('tools/list'),
    { headers: headers(), timeout: TIMEOUT, tags: { scenario: 'discovery' } }
  );
  recordResult(res, 'discovery');
}

function runToolCall() {
  const payload = jsonRpcRequest('tools/call', {
    name: TOOL_NAME,
    arguments: { message: `bench-${Date.now()}` },
  });
  const res = http.post(
    `${GATEWAY_URL}/mcp/tools/call`,
    payload,
    { headers: headers(), timeout: TIMEOUT, tags: { scenario: 'tool_call' } }
  );
  recordResult(res, 'tool_call');
}

function runBurstCalls() {
  // Each VU fires tool calls as fast as possible
  runToolCall();
}

function runSequential() {
  // Simulates a conversation: tool call → small pause → next call
  runToolCall();
  sleep(0.1); // 100ms between calls (realistic agent pace)
}

// --- Main ---

export default function () {
  switch (SCENARIO) {
    case 'discovery':
      runDiscovery();
      break;
    case 'tool_call':
      runToolCall();
      break;
    case 'burst_calls':
      runBurstCalls();
      break;
    case 'sequential':
      runSequential();
      break;
    default:
      runDiscovery();
  }
}

// --- Summary Handler ---

export function handleSummary(data) {
  const metrics = data.metrics;
  const summary = {
    scenario: SCENARIO,
    gateway_url: GATEWAY_URL,
    tool_name: TOOL_NAME,
    timestamp: new Date().toISOString(),
    results: {
      p50_ms: metrics.federation_latency_ms?.values?.['p(50)'] || 0,
      p95_ms: metrics.federation_latency_ms?.values?.['p(95)'] || 0,
      p99_ms: metrics.federation_latency_ms?.values?.['p(99)'] || 0,
      avg_ms: metrics.federation_latency_ms?.values?.avg || 0,
      min_ms: metrics.federation_latency_ms?.values?.min || 0,
      max_ms: metrics.federation_latency_ms?.values?.max || 0,
      success_rate: metrics.federation_success_rate?.values?.rate || 0,
      total_requests: metrics.federation_latency_ms?.values?.count || 0,
      errors: metrics.federation_errors?.values?.count || 0,
    },
    http: {
      reqs_per_sec: metrics.http_reqs?.values?.rate || 0,
      req_duration_p95: metrics.http_req_duration?.values?.['p(95)'] || 0,
    },
  };

  return {
    stdout: JSON.stringify(summary, null, 2) + '\n',
    'federation-results.json': JSON.stringify(summary, null, 2),
  };
}
