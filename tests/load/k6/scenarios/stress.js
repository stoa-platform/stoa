// =============================================================================
// Stress Test - High Load Simulation
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Tests system behavior under heavy load (500 users, 10 minutes)
// NOT for production use
// =============================================================================

import http from 'k6/http';
import { sleep, group, check } from 'k6';
import { getEnv, endpoints, testData, headers } from '../lib/config.js';
import { authGet, authPost, getAuthHeaders } from '../lib/auth.js';
import { checkResponse, checkJsonResponse, errorRate, successRate } from '../lib/checks.js';
import { stressThresholds } from '../thresholds.js';

// Test configuration
export const options = {
  // Aggressive ramping to 500 VUs
  stages: [
    { duration: '1m', target: 100 },   // Ramp to 100
    { duration: '2m', target: 250 },   // Ramp to 250
    { duration: '3m', target: 500 },   // Ramp to 500 (peak load)
    { duration: '2m', target: 500 },   // Stay at peak
    { duration: '1m', target: 250 },   // Ramp down
    { duration: '1m', target: 0 },     // Ramp to 0
  ],

  // Stress test thresholds (more lenient)
  thresholds: stressThresholds,

  // Tags
  tags: {
    testType: 'stress',
  },

  // Don't run in production
  noVUConnectionReuse: false,

  // Summary
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// Abort if running against production
export function setup() {
  const envName = __ENV.ENVIRONMENT || 'dev';
  if (envName === 'prod' || envName === 'production') {
    console.error('STRESS TEST BLOCKED: Cannot run stress tests against production!');
    console.error('Use smoke test for production: k6 run scenarios/smoke.js -e ENVIRONMENT=prod');
    return { abort: true };
  }

  const env = getEnv();
  console.log(`Running STRESS test against: ${env.baseUrl}`);
  console.log(`Target: 500 concurrent users over 10 minutes`);
  console.log('WARNING: This test will generate significant load!');

  return { env, abort: false };
}

// Main test function
export default function (data) {
  if (data.abort) {
    sleep(1);
    return;
  }

  const { env } = data;

  // Weighted scenarios for realistic traffic mix
  const roll = Math.random() * 100;

  if (roll < 40) {
    // 40% - API read operations (most common)
    stressApiReads(env);
  } else if (roll < 60) {
    // 20% - MCP tool operations
    stressMcpOperations(env);
  } else if (roll < 75) {
    // 15% - Tenant operations
    stressTenantOperations(env);
  } else if (roll < 90) {
    // 15% - Write operations (careful in stress)
    stressWriteOperations(env);
  } else {
    // 10% - Health checks (baseline)
    stressHealthChecks(env);
  }

  // Minimal think time under stress
  sleep(0.5 + Math.random() * 0.5);
}

// Stress test scenarios

function stressApiReads(env) {
  group('Stress: API Reads', () => {
    // Rapid-fire API list requests
    for (let i = 0; i < 3; i++) {
      const response = authGet(`${env.baseUrl}${endpoints.controlPlane.apis}`);
      const success = checkResponse(response, `api-list-${i}`);
      errorRate.add(!success);
      successRate.add(success);
    }

    // Deployments list
    const deployResponse = authGet(`${env.baseUrl}${endpoints.controlPlane.deployments}`);
    checkResponse(deployResponse, 'deployments-list');
  });
}

function stressMcpOperations(env) {
  group('Stress: MCP Operations', () => {
    // List tools repeatedly
    for (let i = 0; i < 2; i++) {
      const response = authGet(`${env.mcpUrl}${endpoints.mcp.tools}`);
      checkResponse(response, `tools-list-${i}`);
    }

    // Tool invocation simulation (echo tool)
    const invokeUrl = `${env.mcpUrl}${endpoints.mcp.toolInvoke('echo-tool')}`;
    const invokePayload = JSON.stringify({
      input: {
        message: `Stress test ${Date.now()}`,
      },
    });

    const invokeResponse = authPost(invokeUrl, invokePayload);
    // Accept both success and 404 (tool might not exist)
    check(invokeResponse, {
      'tool invoke completed': (r) => r.status === 200 || r.status === 404 || r.status === 422,
    });
  });
}

function stressTenantOperations(env) {
  group('Stress: Tenant Operations', () => {
    // List tenants
    const listResponse = authGet(`${env.baseUrl}${endpoints.controlPlane.tenants}`);
    const { success, data } = checkJsonResponse(listResponse, 'tenants-list');

    if (success && data) {
      const tenants = Array.isArray(data) ? data : (data.items || []);
      // Get details for first few tenants
      tenants.slice(0, 3).forEach((tenant, i) => {
        const id = tenant.id || tenant.name;
        const detailResponse = authGet(`${env.baseUrl}${endpoints.controlPlane.tenants}/${id}`);
        checkResponse(detailResponse, `tenant-detail-${i}`);
      });
    }
  });
}

function stressWriteOperations(env) {
  group('Stress: Write Operations', () => {
    // Create a temporary API (will be cleaned up)
    const timestamp = Date.now();
    const testApi = {
      name: `stress-test-api-${timestamp}`,
      version: '1.0',
      description: 'Temporary API for stress testing',
      type: 'REST',
    };

    const createResponse = authPost(
      `${env.baseUrl}${endpoints.controlPlane.apis}`,
      JSON.stringify(testApi)
    );

    // Check if created or conflict (already exists)
    const created = check(createResponse, {
      'api created or exists': (r) => r.status === 201 || r.status === 200 || r.status === 409,
    });

    // If created, immediately read it back
    if (created && createResponse.status === 201) {
      const { data } = checkJsonResponse(createResponse, 'created-api');
      if (data && data.id) {
        const readResponse = authGet(`${env.baseUrl}${endpoints.controlPlane.apis}/${data.id}`);
        checkResponse(readResponse, 'read-created-api');
      }
    }
  });
}

function stressHealthChecks(env) {
  group('Stress: Health Checks', () => {
    // All health endpoints in parallel-like fashion
    const responses = [
      http.get(`${env.baseUrl}${endpoints.controlPlane.health}`),
      http.get(`${env.mcpUrl}${endpoints.mcp.health}`),
      http.get(`${env.gatewayUrl}${endpoints.gateway.health}`),
    ];

    responses.forEach((r, i) => {
      check(r, {
        [`health-${i} is 2xx`]: (res) => res.status >= 200 && res.status < 300,
      });
    });
  });
}

// Teardown
export function teardown(data) {
  if (data.abort) {
    console.log('Stress test was blocked (production safety)');
  } else {
    console.log('Stress test completed');
    console.log('Review error rates and response times for capacity planning');
  }
}
