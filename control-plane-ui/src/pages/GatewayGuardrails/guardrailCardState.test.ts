import { describe, expect, it } from 'vitest';
import type { AggregatedMetrics, GuardrailsConfigResponse } from '../../types';
import { guardrailCardState } from './guardrailCardState';

const config: GuardrailsConfigResponse = {
  pii_enabled: true,
  injection_detection_enabled: true,
  prompt_guard_enabled: true,
  content_filter_enabled: true,
  rate_limit_enabled: true,
  opa_policy_enabled: true,
  source: 'env',
  updated_at: '2026-05-09T06:00:00Z',
};

function metrics(
  guardrails: Partial<NonNullable<AggregatedMetrics['guardrails']>> = {}
): AggregatedMetrics {
  return {
    health: {
      total_gateways: 1,
      online: 1,
      offline: 0,
      degraded: 0,
      maintenance: 0,
      health_percentage: 100,
    },
    sync: {
      total_deployments: 1,
      synced: 1,
      pending: 0,
      syncing: 0,
      drifted: 0,
      error: 0,
      deleting: 0,
      sync_percentage: 100,
    },
    overall_status: 'healthy',
    guardrails: {
      pii_detections: 0,
      injection_blocks: 2,
      prompt_guard_blocks: 3,
      content_filter_blocks: 4,
      rate_limit_blocks: 5,
      last_sample_at: '2026-05-09T06:00:00Z',
      metrics_age_seconds: 15,
      source_healthy: true,
      ...guardrails,
    },
  };
}

describe('guardrailCardState', () => {
  it.each([
    {
      name: 'metrics transport error wins',
      cfg: { ...config, pii_enabled: false },
      value: metrics({ source_healthy: true }),
      options: { metricsUnavailable: true },
      expected: 'metrics-unavailable',
    },
    {
      name: 'missing metrics block is unavailable',
      cfg: config,
      value: { ...metrics(), guardrails: undefined },
      options: {},
      expected: 'metrics-unavailable',
    },
    {
      name: 'disabled config wins over healthy count',
      cfg: { ...config, pii_enabled: false },
      value: metrics({ pii_detections: 9 }),
      options: {},
      expected: 'disabled',
    },
    {
      name: 'source unhealthy is unavailable',
      cfg: config,
      value: metrics({ source_healthy: false }),
      options: {},
      expected: 'metrics-unavailable',
    },
    {
      name: 'null sample timestamp is no sample',
      cfg: config,
      value: metrics({ last_sample_at: null, metrics_age_seconds: null }),
      options: {},
      expected: 'no-sample',
    },
    {
      name: 'null count is no sample',
      cfg: config,
      value: metrics({ pii_detections: null }),
      options: {},
      expected: 'no-sample',
    },
    {
      name: 'undefined count is no sample',
      cfg: config,
      value: metrics({ pii_detections: undefined }),
      options: {},
      expected: 'no-sample',
    },
    {
      name: 'non-null timestamp with null age is invalid',
      cfg: config,
      value: metrics({ last_sample_at: '2026-05-09T06:00:00Z', metrics_age_seconds: null }),
      options: {},
      expected: 'metrics-unavailable',
    },
    {
      name: 'exactly 60 seconds is still fresh',
      cfg: config,
      value: metrics({ pii_detections: 0, metrics_age_seconds: 60 }),
      options: {},
      expected: 'healthy',
    },
    {
      name: 'above 60 seconds is stale',
      cfg: config,
      value: metrics({ pii_detections: 0, metrics_age_seconds: 61 }),
      options: {},
      expected: 'stale',
    },
    {
      name: 'healthy zero preserves zero',
      cfg: config,
      value: metrics({ pii_detections: 0 }),
      options: {},
      expected: 'healthy',
      expectedCount: 0,
    },
    {
      name: 'healthy N preserves count',
      cfg: config,
      value: metrics({ pii_detections: 42 }),
      options: {},
      expected: 'healthy',
      expectedCount: 42,
    },
    {
      name: 'rate limit maps to rate_limit_enabled',
      cfg: { ...config, rate_limit_enabled: false },
      value: metrics({ rate_limit_blocks: 4 }),
      field: 'rate_limit_blocks' as const,
      options: {},
      expected: 'disabled',
    },
  ])('$name', ({ cfg, value, field = 'pii_detections', options, expected, expectedCount }) => {
    const state = guardrailCardState(cfg, value, field, options);

    expect(state.kind).toBe(expected);
    if (expectedCount !== undefined) {
      expect(state.count).toBe(expectedCount);
    }
  });
});
