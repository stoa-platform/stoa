import { describe, expect, it } from 'vitest';
import { guardrailCardState } from '../../pages/GatewayGuardrails/guardrailCardState';
import type { AggregatedMetrics, GuardrailsConfigResponse } from '../../types';

const config: GuardrailsConfigResponse = {
  pii_enabled: true,
  injection_detection_enabled: true,
  prompt_guard_enabled: true,
  content_filter_enabled: true,
  rate_limit_enabled: true,
  opa_policy_enabled: true,
  source: 'env',
  updated_at: '2026-05-11T00:00:00Z',
};

function metrics(guardrails: Record<string, unknown>): AggregatedMetrics {
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
      pii_detections: null,
      injection_blocks: null,
      prompt_guard_blocks: null,
      content_filter_blocks: null,
      rate_limit_blocks: null,
      last_sample_at: null,
      metrics_age_seconds: null,
      source_healthy: true,
      ...guardrails,
    },
  } as unknown as AggregatedMetrics;
}

describe('spec/CAB-2214 / CAB-2213 Phase 6.0 red tests', () => {
  it('Phase 6.5 - cp-ui state rendering: AC5 renders server evaluations_zero_trips state', () => {
    const state = guardrailCardState(
      config,
      metrics({
        state: 'evaluations_zero_trips',
        evaluations_count: 12,
        decisions_count: 12,
        trips_count: 0,
        error_count: 0,
        scrape_sample_at: '2026-05-11T00:00:00Z',
        by_guardrail: {
          pii: {
            state: 'evaluations_zero_trips',
            evaluations_count: 12,
            decisions_count: 12,
            trips_count: 0,
            error_count: 0,
            scrape_sample_at: '2026-05-11T00:00:00Z',
            source_healthy: true,
            stale_reason: null,
          },
        },
      }),
      'pii_detections'
    );

    expect(state.kind).toBe('evaluations_zero_trips');
    expect(state.count).toBe(0);
  });

  it('Phase 6.5 - cp-ui state rendering: AC12 trusts backend trips_observed state', () => {
    const state = guardrailCardState(
      config,
      metrics({
        state: 'trips_observed',
        evaluations_count: 20,
        decisions_count: 20,
        trips_count: 3,
        error_count: 1,
        last_evaluation_delta_at: '2026-05-11T00:00:00Z',
        last_decision_delta_at: '2026-05-11T00:00:00Z',
        scrape_sample_at: '2026-05-11T00:00:15Z',
        by_guardrail: {
          pii: {
            state: 'trips_observed',
            evaluations_count: 20,
            decisions_count: 20,
            trips_count: 3,
            error_count: 1,
            last_evaluation_delta_at: '2026-05-11T00:00:00Z',
            last_decision_delta_at: '2026-05-11T00:00:00Z',
            scrape_sample_at: '2026-05-11T00:00:15Z',
            source_healthy: true,
            stale_reason: null,
          },
        },
      }),
      'pii_detections'
    );

    expect(state.kind).toBe('trips_observed');
    expect(state.count).toBe(3);
  });
});
