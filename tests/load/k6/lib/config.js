// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
// =============================================================================
// K6 Load Testing Configuration
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Endpoint configuration for all environments
// =============================================================================

// Environment configuration
export const environments = {
  dev: {
    baseUrl: 'https://api.dev.stoa.cab-i.com',
    gatewayUrl: 'https://gateway.dev.stoa.cab-i.com',
    mcpUrl: 'https://mcp.dev.stoa.cab-i.com',
    keycloakUrl: 'https://auth.dev.stoa.cab-i.com',
    realm: 'stoa',
    clientId: 'stoa-api',
  },
  staging: {
    baseUrl: 'https://api.staging.stoa.cab-i.com',
    gatewayUrl: 'https://gateway.staging.stoa.cab-i.com',
    mcpUrl: 'https://mcp.staging.stoa.cab-i.com',
    keycloakUrl: 'https://auth.staging.stoa.cab-i.com',
    realm: 'stoa',
    clientId: 'stoa-api',
  },
  prod: {
    baseUrl: 'https://api.stoa.cab-i.com',
    gatewayUrl: 'https://gateway.stoa.cab-i.com',
    mcpUrl: 'https://mcp.stoa.cab-i.com',
    keycloakUrl: 'https://auth.stoa.cab-i.com',
    realm: 'stoa',
    clientId: 'stoa-api',
  },
};

// Get current environment from K6 options or default to dev
export function getEnv() {
  const envName = __ENV.ENVIRONMENT || 'dev';
  const env = environments[envName];
  if (!env) {
    throw new Error(`Unknown environment: ${envName}`);
  }
  return env;
}

// API endpoints to test
export const endpoints = {
  // Control-Plane API
  controlPlane: {
    health: '/health',
    apis: '/v1/apis',
    tenants: '/v1/tenants',
    applications: '/v1/applications',
    deployments: '/v1/deployments',
  },

  // MCP Gateway
  mcp: {
    health: '/health',
    tools: '/mcp/v1/tools',
    toolInvoke: (name) => `/mcp/v1/tools/${name}/invoke`,
    toolSets: '/mcp/v1/toolsets',
  },

  // API Gateway Runtime
  gateway: {
    health: '/rest/apigateway/health',
    apis: '/rest/apigateway/apis',
  },
};

// Test data
export const testData = {
  // Sample tenant for testing
  tenant: {
    name: 'load-test-tenant',
    displayName: 'Load Test Tenant',
    description: 'Tenant for load testing',
  },

  // Sample API for testing
  api: {
    name: 'load-test-api',
    version: '1.0',
    description: 'API for load testing',
  },

  // Sample tool invocation
  toolInvoke: {
    toolName: 'echo-tool',
    input: {
      message: 'Load test message',
    },
  },
};

// Request headers
export const headers = {
  json: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
};

export default {
  environments,
  getEnv,
  endpoints,
  testData,
  headers,
};
