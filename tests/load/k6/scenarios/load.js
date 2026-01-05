// =============================================================================
// Load Test - Normal Traffic Simulation
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Simulates expected production load (100 concurrent users, 5 minutes)
// =============================================================================

import http from 'k6/http';
import { sleep, group } from 'k6';
import { getEnv, endpoints, testData } from '../lib/config.js';
import { authGet, authPost } from '../lib/auth.js';
import { checkResponse, checkHealth, checkListResponse, checkJsonResponse } from '../lib/checks.js';
import { sloThresholds } from '../thresholds.js';

// Test configuration
export const options = {
  // Ramping pattern: gradual increase to 100 VUs
  stages: [
    { duration: '30s', target: 20 },   // Ramp up to 20 users
    { duration: '1m', target: 50 },    // Ramp up to 50 users
    { duration: '2m', target: 100 },   // Ramp up to 100 users
    { duration: '1m', target: 100 },   // Stay at 100 users
    { duration: '30s', target: 0 },    // Ramp down to 0
  ],

  // SLO-based thresholds
  thresholds: sloThresholds,

  // Tags
  tags: {
    testType: 'load',
  },

  // Summary
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// Setup
export function setup() {
  const env = getEnv();
  console.log(`Running load test against: ${env.baseUrl}`);
  console.log(`Target: 100 concurrent users over 5 minutes`);

  // Verify services are up before starting load test
  const healthCheck = http.get(`${env.baseUrl}${endpoints.controlPlane.health}`);
  if (healthCheck.status !== 200) {
    console.error('Control-Plane API is not healthy. Aborting test.');
    return { abort: true };
  }

  return { env, abort: false };
}

// Main test function
export default function (data) {
  if (data.abort) {
    console.log('Test aborted due to unhealthy services');
    return;
  }

  const { env } = data;

  // Randomize user behavior
  const scenario = Math.random();

  if (scenario < 0.3) {
    // 30% - Read APIs
    testReadApis(env);
  } else if (scenario < 0.5) {
    // 20% - Read Tenants
    testReadTenants(env);
  } else if (scenario < 0.7) {
    // 20% - MCP Tools
    testMcpTools(env);
  } else if (scenario < 0.85) {
    // 15% - Applications
    testApplications(env);
  } else {
    // 15% - Health checks
    testHealthEndpoints(env);
  }

  // Random think time between 1-3 seconds
  sleep(1 + Math.random() * 2);
}

// Test scenarios

function testReadApis(env) {
  group('Read APIs', () => {
    // List APIs
    const listUrl = `${env.baseUrl}${endpoints.controlPlane.apis}`;
    const listResponse = authGet(listUrl);
    const { success, data } = checkJsonResponse(listResponse, 'list-apis');

    if (success && data && Array.isArray(data) && data.length > 0) {
      // Get first API details
      const apiId = data[0].id || data[0].name;
      const detailUrl = `${env.baseUrl}${endpoints.controlPlane.apis}/${apiId}`;
      const detailResponse = authGet(detailUrl);
      checkResponse(detailResponse, 'get-api-detail');
    }
  });
}

function testReadTenants(env) {
  group('Read Tenants', () => {
    const url = `${env.baseUrl}${endpoints.controlPlane.tenants}`;
    const response = authGet(url);
    checkListResponse(response, 'list-tenants');
  });
}

function testMcpTools(env) {
  group('MCP Tools', () => {
    // List tools
    const listUrl = `${env.mcpUrl}${endpoints.mcp.tools}`;
    const listResponse = authGet(listUrl);
    const { success, data } = checkJsonResponse(listResponse, 'list-tools');

    if (success && data) {
      const tools = Array.isArray(data) ? data : (data.tools || data.items || []);
      if (tools.length > 0) {
        // Get tool details
        const toolName = tools[0].name || tools[0].id;
        const toolUrl = `${env.mcpUrl}${endpoints.mcp.tools}/${toolName}`;
        const toolResponse = authGet(toolUrl);
        checkResponse(toolResponse, 'get-tool-detail');
      }
    }

    // List toolsets
    const toolsetsUrl = `${env.mcpUrl}${endpoints.mcp.toolSets}`;
    const toolsetsResponse = authGet(toolsetsUrl);
    checkListResponse(toolsetsResponse, 'list-toolsets');
  });
}

function testApplications(env) {
  group('Applications', () => {
    const url = `${env.baseUrl}${endpoints.controlPlane.applications}`;
    const response = authGet(url);
    checkListResponse(response, 'list-applications');
  });
}

function testHealthEndpoints(env) {
  group('Health Checks', () => {
    // Control-Plane
    const cpHealth = http.get(`${env.baseUrl}${endpoints.controlPlane.health}`);
    checkHealth(cpHealth, 'control-plane-health');

    // MCP Gateway
    const mcpHealth = http.get(`${env.mcpUrl}${endpoints.mcp.health}`);
    checkHealth(mcpHealth, 'mcp-health');

    // Gateway
    const gwHealth = http.get(`${env.gatewayUrl}${endpoints.gateway.health}`);
    checkResponse(gwHealth, 'gateway-health');
  });
}

// Teardown
export function teardown(data) {
  if (data.abort) {
    console.log('Test was aborted');
  } else {
    console.log('Load test completed');
  }
}
