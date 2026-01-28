// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
// =============================================================================
// Smoke Test - Minimal Load Test
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Quick validation that system is working (safe for production)
// =============================================================================

import http from 'k6/http';
import { sleep } from 'k6';
import { getEnv, endpoints } from '../lib/config.js';
import { authGet } from '../lib/auth.js';
import { checkResponse, checkHealth, checkListResponse } from '../lib/checks.js';
import { smokeThresholds } from '../thresholds.js';

// Test configuration
export const options = {
  // Minimal load: 5 VUs for 30 seconds
  vus: 5,
  duration: '30s',

  // Thresholds (lenient for smoke test)
  thresholds: smokeThresholds,

  // Tags for result filtering
  tags: {
    testType: 'smoke',
  },

  // Summary configuration
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// Setup - run once before tests
export function setup() {
  const env = getEnv();
  console.log(`Running smoke test against: ${env.baseUrl}`);
  console.log(`Environment: ${__ENV.ENVIRONMENT || 'dev'}`);
  return { env };
}

// Main test function
export default function (data) {
  const { env } = data;

  // Test 1: Control-Plane API Health
  {
    const url = `${env.baseUrl}${endpoints.controlPlane.health}`;
    const response = http.get(url, { timeout: '10s' });
    checkHealth(response, 'control-plane-health');
  }

  sleep(1);

  // Test 2: MCP Gateway Health
  {
    const url = `${env.mcpUrl}${endpoints.mcp.health}`;
    const response = http.get(url, { timeout: '10s' });
    checkHealth(response, 'mcp-health');
  }

  sleep(1);

  // Test 3: Gateway Runtime Health
  {
    const url = `${env.gatewayUrl}${endpoints.gateway.health}`;
    const response = http.get(url, { timeout: '10s' });
    checkResponse(response, 'gateway-health');
  }

  sleep(1);

  // Test 4: List APIs (authenticated)
  {
    const url = `${env.baseUrl}${endpoints.controlPlane.apis}`;
    const response = authGet(url, { timeout: '15s' });
    checkListResponse(response, 'list-apis');
  }

  sleep(1);

  // Test 5: List MCP Tools
  {
    const url = `${env.mcpUrl}${endpoints.mcp.tools}`;
    const response = authGet(url, { timeout: '15s' });
    checkListResponse(response, 'list-tools');
  }

  sleep(1);
}

// Teardown - run once after all tests
export function teardown(data) {
  console.log('Smoke test completed');
}
