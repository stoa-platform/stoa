import type {
  AggregatedMetrics,
  GuardrailKey,
  GuardrailRuntimeMetrics,
  GuardrailsConfigResponse,
  GuardrailsMetricField,
  GuardrailsState,
} from '../../types';

export type GuardrailCardStateKind = GuardrailsState | 'disabled';

export interface GuardrailCardUIState {
  kind: GuardrailCardStateKind;
  count: number | null;
  evaluationsCount: number | null;
  tripsCount: number | null;
  lastObservedAt: string | null;
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

const METRIC_TO_GUARDRAIL: Record<GuardrailsMetricField, GuardrailKey> = {
  pii_detections: 'pii',
  injection_blocks: 'injection',
  prompt_guard_blocks: 'prompt_guard',
  content_filter_blocks: 'content_filter',
  rate_limit_blocks: 'rate_limit',
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
    return {
      kind: 'disabled',
      count: null,
      evaluationsCount: null,
      tripsCount: null,
      lastObservedAt: null,
    };
  }

  const guardrailKey = METRIC_TO_GUARDRAIL[fieldName];
  const guardrail = metrics.guardrails.by_guardrail?.[guardrailKey];
  if (!guardrail) {
    return unavailableState();
  }

  return stateFromBackend(guardrail);
}

function unavailableState(): GuardrailCardUIState {
  return {
    kind: 'metrics_unavailable',
    count: null,
    evaluationsCount: null,
    tripsCount: null,
    lastObservedAt: null,
  };
}

function stateFromBackend(guardrail: GuardrailRuntimeMetrics): GuardrailCardUIState {
  return {
    kind: guardrail.state,
    count: guardrail.trips_count,
    evaluationsCount: guardrail.evaluations_count,
    tripsCount: guardrail.trips_count,
    lastObservedAt: guardrail.last_evaluation_delta_at ?? guardrail.scrape_sample_at,
  };
}
