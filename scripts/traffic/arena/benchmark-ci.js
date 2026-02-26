/**
 * Gateway CI Benchmark — Simplified k6 script for PR performance regression gate.
 *
 * Lighter version of benchmark.js with 3 scenarios (vs 8) for fast CI feedback.
 * Total duration: ~30s (vs ~3 min for full arena).
 *
 * Env vars:
 *   TARGET_URL   — URL to benchmark (default: http://localhost:8090/echo/get)
 *   HEALTH_URL   — Health check URL (default: http://localhost:8090/health)
 *   SCENARIO     — One of: health, sequential, burst_50
 *   SUMMARY_FILE — Path to write JSON summary (default: /tmp/summary.json)
 *   TIMEOUT      — Request timeout in seconds (default: 5)
 */

import http from 'k6/http';
import { check } from 'k6';

const TARGET_URL = __ENV.TARGET_URL || 'http://localhost:8090/echo/get';
const HEALTH_URL = __ENV.HEALTH_URL || 'http://localhost:8090/health';
const SCENARIO = __ENV.SCENARIO || 'health';
const TIMEOUT = (__ENV.TIMEOUT || '5') + 's';

const scenarios = {
  health: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 5,
    maxDuration: '10s',
  },
  sequential: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 20,
    maxDuration: '30s',
  },
  burst_50: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '3s', target: 50 },
      { duration: '7s', target: 50 },
      { duration: '2s', target: 0 },
    ],
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

export default function () {
  const url = SCENARIO === 'health' ? HEALTH_URL : TARGET_URL;
  const params = {
    timeout: TIMEOUT,
    tags: { scenario: SCENARIO },
  };

  const res = http.get(url, params);

  check(res, {
    'status < 500': (r) => r.status < 500,
    'status is 2xx': (r) => r.status >= 200 && r.status < 300,
  });
}

export function handleSummary(data) {
  const summaryFile = __ENV.SUMMARY_FILE || '/tmp/summary.json';
  const out = {};
  out[summaryFile] = JSON.stringify(data, null, 2);
  return out;
}
