import type {
  AggregatedMetrics,
  GuardrailsConfigResponse,
  GuardrailsMetricField,
} from '../../types';

export type GuardrailCardStateKind =
  | 'metrics-unavailable'
  | 'disabled'
  | 'no-sample'
  | 'stale'
  | 'healthy';

export interface GuardrailCardUIState {
  kind: GuardrailCardStateKind;
  count: number | null;
  lastSampleAt: string | null;
}

export interface GuardrailCardStateOptions {
  metricsUnavailable?: boolean;
}

const METRIC_TO_CONFIG_FIELD: Record<GuardrailsMetricField, keyof GuardrailsConfigResponse> = {
  pii_detections: 'pii_enabled',
  injection_blocks: 'injection_detection_enabled',
  prompt_guard_blocks: 'prompt_guard_enabled',
  content_filter_blocks: 'content_filter_enabled',
  rate_limit_blocks: 'rate_limit_enabled',
};

export function guardrailCardState(
  config: GuardrailsConfigResponse | null,
  metrics: AggregatedMetrics | null,
  fieldName: GuardrailsMetricField,
  options: GuardrailCardStateOptions = {}
): GuardrailCardUIState {
  if (options.metricsUnavailable || !metrics?.guardrails) {
    return unavailableState();
  }

  const configField = METRIC_TO_CONFIG_FIELD[fieldName];
  if (config && config[configField] === false) {
    return { kind: 'disabled', count: null, lastSampleAt: null };
  }

  const guardrails = metrics.guardrails;
  if (guardrails.source_healthy !== true) {
    return unavailableState();
  }

  const count = guardrails[fieldName];
  if (guardrails.last_sample_at === null || count === null || count === undefined) {
    return { kind: 'no-sample', count: null, lastSampleAt: null };
  }

  if (guardrails.metrics_age_seconds === null || guardrails.metrics_age_seconds === undefined) {
    return unavailableState();
  }

  if (guardrails.metrics_age_seconds > 60) {
    return { kind: 'stale', count, lastSampleAt: guardrails.last_sample_at };
  }

  return { kind: 'healthy', count, lastSampleAt: guardrails.last_sample_at };
}

function unavailableState(): GuardrailCardUIState {
  return { kind: 'metrics-unavailable', count: null, lastSampleAt: null };
}
