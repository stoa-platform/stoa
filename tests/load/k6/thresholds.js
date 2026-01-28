// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
// =============================================================================
// K6 Performance Thresholds (SLO-based)
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Defines pass/fail criteria based on SLO objectives
// =============================================================================

/**
 * SLO-based thresholds for all test scenarios
 *
 * SLO Objectives:
 * - Availability: 99.9%
 * - Latency p95: < 500ms
 * - Latency p99: < 1000ms
 * - Error Rate: < 0.1%
 */
export const sloThresholds = {
  // HTTP request duration (latency)
  'http_req_duration': [
    'p(50)<200',   // 50% of requests under 200ms
    'p(95)<500',   // 95% of requests under 500ms (SLO)
    'p(99)<1000',  // 99% of requests under 1000ms (SLO)
    'max<3000',    // No request over 3s
  ],

  // HTTP request failures
  'http_req_failed': [
    'rate<0.001',  // Less than 0.1% errors (SLO)
  ],

  // Request rate (throughput)
  'http_reqs': [
    'rate>10',     // At least 10 requests/second sustained
  ],

  // Custom error rate metric
  'errors': [
    'rate<0.01',   // Less than 1% custom errors
  ],

  // Custom success rate metric
  'success': [
    'rate>0.99',   // At least 99% success rate
  ],

  // API latency trend (custom metric)
  'api_latency': [
    'p(95)<500',
    'p(99)<1000',
  ],
};

/**
 * Relaxed thresholds for smoke tests
 * Used in production with minimal load
 */
export const smokeThresholds = {
  'http_req_duration': [
    'p(95)<1000',  // More lenient for smoke tests
    'p(99)<2000',
  ],
  'http_req_failed': [
    'rate<0.05',   // 5% error tolerance for smoke
  ],
};

/**
 * Strict thresholds for stress tests
 * Expecting some degradation under heavy load
 */
export const stressThresholds = {
  'http_req_duration': [
    'p(50)<500',
    'p(95)<2000',  // Higher tolerance under stress
    'p(99)<5000',
  ],
  'http_req_failed': [
    'rate<0.05',   // 5% errors acceptable under stress
  ],
  'http_reqs': [
    'rate>50',     // Minimum 50 req/s under stress
  ],
};

/**
 * Spike test thresholds
 * Expecting recovery after spike
 */
export const spikeThresholds = {
  'http_req_duration': [
    'p(95)<3000',  // Very lenient during spike
    'p(99)<10000',
  ],
  'http_req_failed': [
    'rate<0.10',   // 10% errors acceptable during spike
  ],
};

/**
 * Get thresholds based on test type
 */
export function getThresholds(testType = 'load') {
  switch (testType.toLowerCase()) {
    case 'smoke':
      return smokeThresholds;
    case 'stress':
      return stressThresholds;
    case 'spike':
      return spikeThresholds;
    case 'load':
    default:
      return sloThresholds;
  }
}

/**
 * Merge custom thresholds with defaults
 */
export function mergeThresholds(customThresholds, baseType = 'load') {
  const base = getThresholds(baseType);
  return {
    ...base,
    ...customThresholds,
  };
}

export default {
  sloThresholds,
  smokeThresholds,
  stressThresholds,
  spikeThresholds,
  getThresholds,
  mergeThresholds,
};
