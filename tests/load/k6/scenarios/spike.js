// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
// =============================================================================
// Spike Test - Sudden Load Surge Simulation
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Tests system behavior under sudden traffic spike (1000 users spike)
// NOT for production use
// =============================================================================

import http from 'k6/http';
import { sleep, group, check } from 'k6';
import { getEnv, endpoints } from '../lib/config.js';
import { authGet } from '../lib/auth.js';
import { checkResponse, checkHealth, errorRate, successRate, apiLatency } from '../lib/checks.js';
import { spikeThresholds } from '../thresholds.js';

// Test configuration
export const options = {
  // Spike pattern: sudden surge then recovery
  stages: [
    { duration: '30s', target: 50 },    // Warm up
    { duration: '10s', target: 1000 },  // SPIKE! Instant jump to 1000 users
    { duration: '1m', target: 1000 },   // Hold spike
    { duration: '10s', target: 50 },    // Quick drop
    { duration: '2m', target: 50 },     // Recovery period
    { duration: '30s', target: 0 },     // Ramp down
  ],

  // Spike thresholds (very lenient during spike)
  thresholds: spikeThresholds,

  // Tags
  tags: {
    testType: 'spike',
  },

  // Summary
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// Block production execution
export function setup() {
  const envName = __ENV.ENVIRONMENT || 'dev';
  if (envName === 'prod' || envName === 'production') {
    console.error('SPIKE TEST BLOCKED: Cannot run spike tests against production!');
    return { abort: true };
  }

  const env = getEnv();
  console.log(`Running SPIKE test against: ${env.baseUrl}`);
  console.log('WARNING: This test will create a sudden 1000 user spike!');
  console.log('Purpose: Test autoscaling and recovery behavior');

  // Baseline health check
  const healthResponse = http.get(`${env.baseUrl}${endpoints.controlPlane.health}`);
  if (healthResponse.status !== 200) {
    console.error('Service not healthy before spike test');
    return { abort: true };
  }

  return {
    env,
    abort: false,
    startTime: Date.now(),
  };
}

// Main test function
export default function (data) {
  if (data.abort) {
    sleep(1);
    return;
  }

  const { env, startTime } = data;
  const elapsed = (Date.now() - startTime) / 1000;

  // Determine test phase for logging
  let phase = 'warmup';
  if (elapsed > 30 && elapsed <= 40) phase = 'spike-start';
  else if (elapsed > 40 && elapsed <= 100) phase = 'spike-hold';
  else if (elapsed > 100 && elapsed <= 110) phase = 'spike-drop';
  else if (elapsed > 110 && elapsed <= 230) phase = 'recovery';
  else if (elapsed > 230) phase = 'cooldown';

  // Simple workload during spike - focus on read operations
  spikeWorkload(env, phase);

  // Minimal sleep - maximize pressure
  sleep(0.1 + Math.random() * 0.2);
}

function spikeWorkload(env, phase) {
  group(`Spike ${phase}`, () => {
    // Primary: Health checks (lightweight, good for measuring basic responsiveness)
    const healthStart = Date.now();
    const healthResponse = http.get(`${env.baseUrl}${endpoints.controlPlane.health}`, {
      timeout: '30s',  // Generous timeout during spike
    });
    const healthDuration = Date.now() - healthStart;

    const healthOk = check(healthResponse, {
      'health responds': (r) => r.status !== 0,  // Any response is good during spike
      'health is 2xx': (r) => r.status >= 200 && r.status < 300,
    });

    errorRate.add(!healthOk);
    successRate.add(healthOk);
    apiLatency.add(healthDuration);

    // Secondary: API list (more resource intensive)
    const apiStart = Date.now();
    const apiResponse = authGet(`${env.baseUrl}${endpoints.controlPlane.apis}`, {
      timeout: '60s',
    });
    const apiDuration = Date.now() - apiStart;

    const apiOk = check(apiResponse, {
      'api list responds': (r) => r.status !== 0,
      'api list is 2xx or 429': (r) => (r.status >= 200 && r.status < 300) || r.status === 429,
    });

    errorRate.add(!apiOk);
    successRate.add(apiOk);
    apiLatency.add(apiDuration);

    // Track rate limiting during spike
    if (apiResponse.status === 429) {
      console.log(`Rate limited at phase: ${phase}`);
    }
  });
}

// Teardown with recovery analysis
export function teardown(data) {
  if (data.abort) {
    console.log('Spike test was blocked');
    return;
  }

  console.log('='.repeat(60));
  console.log('Spike Test Completed');
  console.log('='.repeat(60));
  console.log('');
  console.log('Key metrics to analyze:');
  console.log('1. Response time during spike vs baseline');
  console.log('2. Error rate during spike period');
  console.log('3. Recovery time after spike ends');
  console.log('4. Rate limiting behavior (429 responses)');
  console.log('5. Autoscaling events (check Kubernetes HPA)');
  console.log('');
  console.log('Check Kubernetes for:');
  console.log('  kubectl get hpa -n stoa-system');
  console.log('  kubectl get pods -n stoa-system');
  console.log('');
}

// Custom summary handler for spike analysis
export function handleSummary(data) {
  // Calculate spike-specific metrics
  const metrics = data.metrics;

  const summary = {
    testType: 'spike',
    timestamp: new Date().toISOString(),
    peakVUs: 1000,
    results: {
      totalRequests: metrics.http_reqs?.values?.count || 0,
      errorRate: metrics.http_req_failed?.values?.rate || 0,
      latency: {
        avg: metrics.http_req_duration?.values?.avg || 0,
        p95: metrics.http_req_duration?.values?.['p(95)'] || 0,
        p99: metrics.http_req_duration?.values?.['p(99)'] || 0,
        max: metrics.http_req_duration?.values?.max || 0,
      },
    },
    thresholdsPassed: Object.entries(data.root_group?.checks || {})
      .filter(([_, v]) => v.passes > 0)
      .length,
  };

  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'spike-summary.json': JSON.stringify(summary, null, 2),
  };
}

// Import text summary helper
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';
