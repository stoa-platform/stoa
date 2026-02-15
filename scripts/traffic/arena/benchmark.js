/**
 * Gateway Arena — k6 Benchmark Script
 *
 * Single k6 script that runs one scenario at a time, controlled by env vars.
 * Called multiple times by the orchestrator (run-arena.sh) for each scenario.
 *
 * Env vars:
 *   TARGET_URL   — URL to benchmark (proxy or health endpoint)
 *   HEALTH_URL   — Health check URL (used only by warmup scenario)
 *   SCENARIO     — One of: warmup, health, sequential, burst_10, burst_50, burst_100, sustained, ramp_up
 *   HEADERS      — JSON object of extra headers (optional)
 *   TIMEOUT      — Request timeout in seconds (default: 5)
 */

import http from 'k6/http';
import { check } from 'k6';

const TARGET_URL = __ENV.TARGET_URL || 'http://localhost:8080/echo/get';
const HEALTH_URL = __ENV.HEALTH_URL || 'http://localhost:8080/health';
const SCENARIO = __ENV.SCENARIO || 'health';
const HEADERS = __ENV.HEADERS ? JSON.parse(__ENV.HEADERS) : {};
const TIMEOUT = (__ENV.TIMEOUT || '5') + 's';

// Scenario definitions: VUs x iterations or duration
const scenarios = {
  warmup: {
    executor: 'shared-iterations',
    vus: 10,
    iterations: 50,
    maxDuration: '15s',
  },
  health: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 1,
    maxDuration: '10s',
  },
  sequential: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 20,
    maxDuration: '30s',
  },
  burst_10: {
    executor: 'shared-iterations',
    vus: 10,
    iterations: 10,
    maxDuration: '15s',
  },
  burst_50: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '5s', target: 50 },   // ramp-up
      { duration: '10s', target: 50 },  // hold
      { duration: '3s', target: 0 },    // ramp-down
    ],
  },
  burst_100: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '5s', target: 100 },  // ramp-up
      { duration: '10s', target: 100 }, // hold
      { duration: '3s', target: 0 },    // ramp-down
    ],
  },
  sustained: {
    executor: 'shared-iterations',
    vus: 1,
    iterations: 100,
    maxDuration: '60s',
  },
  ramp_up: {
    executor: 'ramping-arrival-rate',
    startRate: 10,
    timeUnit: '1s',
    preAllocatedVUs: 50,
    maxVUs: 100,
    stages: [
      { duration: '5s', target: 10 },    // warm
      { duration: '10s', target: 30 },   // ramp
      { duration: '10s', target: 60 },   // push
      { duration: '10s', target: 100 },  // peak
      { duration: '15s', target: 100 },  // sustain at peak
      { duration: '10s', target: 10 },   // cool down
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
  // Disable default thresholds — we score externally
  thresholds: {},
};

export default function () {
  const url = SCENARIO === 'warmup' ? TARGET_URL : (SCENARIO === 'health' ? HEALTH_URL : TARGET_URL);
  const params = {
    headers: HEADERS,
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
