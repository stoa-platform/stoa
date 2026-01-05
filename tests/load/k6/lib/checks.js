// =============================================================================
// K6 Common Check Assertions
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Reusable check functions for consistent test assertions
// =============================================================================

import { check, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
export const errorRate = new Rate('errors');
export const successRate = new Rate('success');
export const apiLatency = new Trend('api_latency', true);
export const requestCount = new Counter('requests');

/**
 * Standard HTTP response checks
 */
export function checkResponse(response, name = 'request') {
  const checks = {
    [`${name} status is 2xx`]: (r) => r.status >= 200 && r.status < 300,
    [`${name} has body`]: (r) => r.body && r.body.length > 0,
    [`${name} response time < 500ms`]: (r) => r.timings.duration < 500,
  };

  const success = check(response, checks);

  // Record metrics
  errorRate.add(!success);
  successRate.add(success);
  apiLatency.add(response.timings.duration);
  requestCount.add(1);

  return success;
}

/**
 * Check for successful status codes (2xx)
 */
export function checkStatus2xx(response, name = 'request') {
  return check(response, {
    [`${name} returns 2xx`]: (r) => r.status >= 200 && r.status < 300,
  });
}

/**
 * Check for specific status code
 */
export function checkStatus(response, expectedStatus, name = 'request') {
  return check(response, {
    [`${name} returns ${expectedStatus}`]: (r) => r.status === expectedStatus,
  });
}

/**
 * Check response time thresholds
 */
export function checkLatency(response, thresholds = {}) {
  const { p50 = 200, p95 = 500, p99 = 1000 } = thresholds;

  return check(response, {
    [`latency < ${p50}ms (target p50)`]: (r) => r.timings.duration < p50,
    [`latency < ${p95}ms (SLO p95)`]: (r) => r.timings.duration < p95,
    [`latency < ${p99}ms (SLO p99)`]: (r) => r.timings.duration < p99,
  });
}

/**
 * Check JSON response structure
 */
export function checkJsonResponse(response, name = 'request') {
  let parsed = null;

  const isJson = check(response, {
    [`${name} is valid JSON`]: (r) => {
      try {
        parsed = JSON.parse(r.body);
        return true;
      } catch {
        return false;
      }
    },
  });

  return { success: isJson, data: parsed };
}

/**
 * Check health endpoint response
 */
export function checkHealth(response, name = 'health') {
  const { success, data } = checkJsonResponse(response, name);

  if (!success) return false;

  return check(response, {
    [`${name} status is healthy`]: () =>
      data.status === 'healthy' ||
      data.status === 'ok' ||
      data.status === 'UP' ||
      data.healthy === true,
  });
}

/**
 * Check list/collection response
 */
export function checkListResponse(response, name = 'list') {
  const { success, data } = checkJsonResponse(response, name);

  if (!success) return false;

  return check(response, {
    [`${name} returns array or items`]: () =>
      Array.isArray(data) ||
      (data.items && Array.isArray(data.items)) ||
      (data.data && Array.isArray(data.data)),
  });
}

/**
 * Check error response format
 */
export function checkErrorResponse(response, expectedStatus, name = 'error') {
  const { success, data } = checkJsonResponse(response, name);

  return check(response, {
    [`${name} has expected status ${expectedStatus}`]: (r) => r.status === expectedStatus,
    [`${name} has error message`]: () =>
      success && (data.message || data.error || data.detail),
  });
}

/**
 * Group checks for a specific endpoint
 */
export function checkEndpoint(name, fn) {
  return group(name, () => {
    const result = fn();
    return result;
  });
}

/**
 * Retry a check with backoff
 */
export function retryCheck(fn, maxRetries = 3, delayMs = 1000) {
  let lastResult = null;

  for (let i = 0; i < maxRetries; i++) {
    lastResult = fn();
    if (lastResult) return true;

    if (i < maxRetries - 1) {
      // Simple sleep using Date
      const start = Date.now();
      while (Date.now() - start < delayMs) {
        // Busy wait (K6 doesn't have setTimeout)
      }
    }
  }

  return false;
}

export default {
  errorRate,
  successRate,
  apiLatency,
  requestCount,
  checkResponse,
  checkStatus2xx,
  checkStatus,
  checkLatency,
  checkJsonResponse,
  checkHealth,
  checkListResponse,
  checkErrorResponse,
  checkEndpoint,
  retryCheck,
};
