import { describe, expect, it } from 'vitest';
import type {
  AggregatedMetrics,
  GuardrailKey,
  GuardrailRuntimeMetrics,
  GuardrailsConfigResponse,
  GuardrailsState,
} from '../../types';
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

const GUARDRAILS: GuardrailKey[] = [
  'pii',
  'injection',
  'prompt_guard',
  'content_filter',
  'rate_limit',
];

function entry(
  state: GuardrailsState = 'trips_observed',
  overrides: Partial<GuardrailRuntimeMetrics> = {}
): GuardrailRuntimeMetrics {
  return {
    state,
    evaluations_count: state === 'metrics_unavailable' ? null : 10,
    decisions_count: state === 'metrics_unavailable' ? null : 10,
    trips_count: state === 'metrics_unavailable' ? null : 5,
    error_count: state === 'metrics_unavailable' ? null : 0,
    last_evaluation_delta_at: '2026-05-09T06:00:00Z',
    last_decision_delta_at: '2026-05-09T06:00:00Z',
    scrape_sample_at: '2026-05-09T06:00:15Z',
    source_healthy: state !== 'metrics_unavailable' && state !== 'stale_data',
    stale_reason: state === 'metrics_unavailable' ? 'prom_unreachable' : null,
    ...overrides,
  };
}

function metrics(
  pii: GuardrailRuntimeMetrics = entry(),
  topState: GuardrailsState = 'trips_observed'
): AggregatedMetrics {
  const by_guardrail = Object.fromEntries(
    GUARDRAILS.map((key) => [key, key === 'pii' ? pii : entry()])
  ) as Record<GuardrailKey, GuardrailRuntimeMetrics>;

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
      state: topState,
      evaluations_count: 10,
      decisions_count: 10,
      trips_count: 5,
      error_count: 0,
      pii_detections: 5,
      injection_blocks: 2,
      prompt_guard_blocks: 3,
      content_filter_blocks: 4,
      rate_limit_blocks: 5,
      last_evaluation_delta_at: '2026-05-09T06:00:00Z',
      last_decision_delta_at: '2026-05-09T06:00:00Z',
      scrape_sample_at: '2026-05-09T06:00:15Z',
      stale_reason: null,
      by_guardrail,
      last_sample_at: '2026-05-09T06:00:15Z',
      metrics_age_seconds: 15,
      source_healthy: true,
    },
  };
}

describe('guardrailCardState', () => {
  it('keeps transport errors and disabled config out of backend state rendering', () => {
    expect(
      guardrailCardState(config, metrics(), 'pii_detections', { metricsUnavailable: true })
    ).toMatchObject({ kind: 'metrics_unavailable' });
    expect(
      guardrailCardState({ ...config, pii_enabled: false }, metrics(), 'pii_detections').kind
    ).toBe('disabled');
  });

  it.each([
    ['metrics_unavailable', entry('metrics_unavailable', { trips_count: null }), null, null],
    ['no_evaluations', entry('no_evaluations', { evaluations_count: 0, trips_count: 0 }), 0, 0],
    [
      'evaluations_zero_trips',
      entry('evaluations_zero_trips', { evaluations_count: 12, trips_count: 0 }),
      0,
      12,
    ],
    ['trips_observed', entry('trips_observed', { trips_count: 42 }), 42, 10],
    [
      'stale_data',
      entry('stale_data', {
        last_evaluation_delta_at: null,
        scrape_sample_at: '2026-05-09T06:00:15Z',
      }),
      5,
      10,
    ],
  ] as const)('renders backend state %s verbatim', (expected, guardrail, count, evaluations) => {
    const state = guardrailCardState(config, metrics(guardrail), 'pii_detections');

    expect(state.kind).toBe(expected);
    expect(state.count).toBe(count);
    expect(state.evaluationsCount).toBe(evaluations);
  });

  it('does not collapse null trip counts into zero', () => {
    const state = guardrailCardState(
      config,
      metrics(entry('evaluations_zero_trips', { evaluations_count: null, trips_count: null })),
      'pii_detections'
    );

    expect(state.kind).toBe('evaluations_zero_trips');
    expect(state.count).toBeNull();
    expect(state.evaluationsCount).toBeNull();
  });

  it('uses per-guardrail state even when top-level state differs', () => {
    const state = guardrailCardState(
      config,
      metrics(entry('stale_data', { scrape_sample_at: '2026-05-09T06:00:15Z' }), 'trips_observed'),
      'pii_detections'
    );

    expect(state.kind).toBe('stale_data');
    expect(state.lastObservedAt).toBe('2026-05-09T06:00:00Z');
  });
});
