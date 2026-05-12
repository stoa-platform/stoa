import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';
import type {
  AggregatedMetrics,
  GuardrailKey,
  GuardrailRuntimeMetrics,
  GuardrailsConfigResponse,
  GuardrailsMetricsBlock,
} from '../../types';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetGatewayAggregatedMetrics = vi.fn();
const mockGetGuardrailsConfig = vi.fn();
const mockGetGuardrailsEvents = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayAggregatedMetrics: (...args: unknown[]) => mockGetGatewayAggregatedMetrics(...args),
    getGuardrailsConfig: (...args: unknown[]) => mockGetGuardrailsConfig(...args),
    getGuardrailsEvents: (...args: unknown[]) => mockGetGuardrailsEvents(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

import { GuardrailsDashboard } from './GuardrailsDashboard';

const enabledConfig: GuardrailsConfigResponse = {
  pii_enabled: true,
  injection_detection_enabled: true,
  prompt_guard_enabled: true,
  content_filter_enabled: true,
  rate_limit_enabled: true,
  opa_policy_enabled: true,
  source: 'env',
  updated_at: new Date(Date.now() - 30_000).toISOString(),
};

const GUARDRAILS: GuardrailKey[] = [
  'pii',
  'injection',
  'prompt_guard',
  'content_filter',
  'rate_limit',
];

function guardrailEntry(overrides: Partial<GuardrailRuntimeMetrics> = {}): GuardrailRuntimeMetrics {
  return {
    state: 'trips_observed',
    evaluations_count: 10,
    decisions_count: 10,
    trips_count: 5,
    error_count: 0,
    last_evaluation_delta_at: '2026-05-09T06:00:00Z',
    last_decision_delta_at: '2026-05-09T06:00:00Z',
    scrape_sample_at: '2026-05-09T06:00:15Z',
    source_healthy: true,
    stale_reason: null,
    ...overrides,
  };
}

function byGuardrail(
  overrides: Partial<Record<GuardrailKey, Partial<GuardrailRuntimeMetrics>>> = {}
): Record<GuardrailKey, GuardrailRuntimeMetrics> {
  return GUARDRAILS.reduce(
    (acc, guardrail) => {
      acc[guardrail] = guardrailEntry(overrides[guardrail]);
      return acc;
    },
    {} as Record<GuardrailKey, GuardrailRuntimeMetrics>
  );
}

function metrics(
  guardrails: Partial<GuardrailsMetricsBlock> = {},
  perGuardrail: Partial<Record<GuardrailKey, Partial<GuardrailRuntimeMetrics>>> = {}
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
      state: 'trips_observed',
      evaluations_count: 10,
      decisions_count: 10,
      trips_count: 5,
      error_count: 0,
      pii_detections: 5,
      injection_blocks: 2,
      prompt_guard_blocks: 1,
      content_filter_blocks: 0,
      rate_limit_blocks: 0,
      last_evaluation_delta_at: '2026-05-09T06:00:00Z',
      last_decision_delta_at: '2026-05-09T06:00:00Z',
      scrape_sample_at: '2026-05-09T06:00:15Z',
      stale_reason: null,
      by_guardrail: byGuardrail(perGuardrail),
      last_sample_at: new Date(Date.now() - 15_000).toISOString(),
      metrics_age_seconds: 15,
      source_healthy: true,
      ...guardrails,
    },
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

describe('GuardrailsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetGuardrailsConfig.mockResolvedValue(enabledConfig);
    mockGetGatewayAggregatedMetrics.mockResolvedValue(metrics());
    mockGetGuardrailsEvents.mockResolvedValue({ events: [], total: 0 });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the AR-1 heading and subtitle', async () => {
    renderWithProviders(<GuardrailsDashboard />);
    expect(
      await screen.findByRole('heading', { name: /Security & Guardrails/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring'
      )
    ).toBeInTheDocument();
  });

  it('config panel renders enabled and disabled state from /guardrails/config', async () => {
    mockGetGuardrailsConfig.mockResolvedValue({
      ...enabledConfig,
      injection_detection_enabled: false,
      opa_policy_enabled: false,
    });

    renderWithProviders(<GuardrailsDashboard />);

    expect(await screen.findByText('Guardrail Configuration')).toBeInTheDocument();
    expect(
      within(screen.getByTestId('config-pii-detection')).getByText('Enabled')
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('config-injection-detection')).getByText('Disabled')
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('config-opa-policy')).getByText('Disabled')
    ).toBeInTheDocument();
  });

  it('card state is disabled when config is false', async () => {
    mockGetGuardrailsConfig.mockResolvedValue({ ...enabledConfig, pii_enabled: false });

    renderWithProviders(<GuardrailsDashboard />);

    expect(
      await within(screen.getByTestId('guardrail-card-pii-detection')).findByText('Disabled')
    ).toBeInTheDocument();
  });

  it('card state renders evaluations with zero trips from backend state', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics(
        {},
        { pii: { state: 'evaluations_zero_trips', evaluations_count: 12, trips_count: 0 } }
      )
    );

    renderWithProviders(<GuardrailsDashboard />);

    await waitFor(() => {
      expect(
        within(screen.getByTestId('guardrail-card-pii-detection')).getByText(
          '0 trips after 12 evaluations'
        )
      ).toBeInTheDocument();
    });
  });

  it('card state renders observed trips from backend state', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics({}, { injection: { state: 'trips_observed', trips_count: 7 } })
    );

    renderWithProviders(<GuardrailsDashboard />);

    expect(await screen.findByText('7 trips observed')).toBeInTheDocument();
  });

  it('card state renders no evaluations from backend state', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics({}, { pii: { state: 'no_evaluations', evaluations_count: 0, trips_count: 0 } })
    );

    renderWithProviders(<GuardrailsDashboard />);

    expect(
      await within(screen.getByTestId('guardrail-card-pii-detection')).findByText(
        'No guardrail evaluations in window'
      )
    ).toBeInTheDocument();
  });

  it('null counts do not collapse into zero text', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics(
        {},
        {
          pii: {
            state: 'evaluations_zero_trips',
            evaluations_count: null,
            trips_count: null,
          },
        }
      )
    );

    renderWithProviders(<GuardrailsDashboard />);

    expect(
      await screen.findByText('Guardrail evaluations observed; trip count unavailable')
    ).toBeInTheDocument();
    const card = screen.getByTestId('guardrail-card-pii-detection');
    expect(within(card).queryByText(/0 trips/)).not.toBeInTheDocument();
  });

  it('current prod fail-closed config can show config unavailable while metrics show no evaluations', async () => {
    mockGetGuardrailsConfig.mockRejectedValue(new Error('guardrails env missing'));
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics({}, { pii: { state: 'no_evaluations', evaluations_count: 0, trips_count: 0 } })
    );

    renderWithProviders(<GuardrailsDashboard />);

    expect(await screen.findAllByText('Metrics unavailable')).not.toHaveLength(0);
    expect(
      await within(screen.getByTestId('guardrail-card-pii-detection')).findByText(
        'No guardrail evaluations in window'
      )
    ).toBeInTheDocument();
  });

  it('card state renders stale data from backend state', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics(
        { state: 'trips_observed', metrics_age_seconds: 15 },
        {
          pii: {
            state: 'stale_data',
            last_evaluation_delta_at: null,
            scrape_sample_at: '2026-05-09T06:00:15Z',
          },
        }
      )
    );

    renderWithProviders(<GuardrailsDashboard />);

    expect(
      await within(screen.getByTestId('guardrail-card-pii-detection')).findByText(
        'Data stale (last observed: 2026-05-09T06:00:15Z)'
      )
    ).toBeInTheDocument();
  });

  it('card state renders metrics unavailable from backend state', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics({}, { pii: { state: 'metrics_unavailable', trips_count: null } })
    );

    renderWithProviders(<GuardrailsDashboard />);

    expect(
      await within(screen.getByTestId('guardrail-card-pii-detection')).findByText(
        'Metrics unavailable'
      )
    ).toBeInTheDocument();
  });

  it('card state renders metrics unavailable on metrics HTTP error', async () => {
    mockGetGatewayAggregatedMetrics.mockRejectedValue(new Error('metrics 503'));

    renderWithProviders(<GuardrailsDashboard />);

    expect(
      await within(screen.getByTestId('guardrail-card-pii-detection')).findByText(
        'Metrics unavailable'
      )
    ).toBeInTheDocument();
  });

  it('time range selector propagates to metrics and events fetch', async () => {
    renderWithProviders(<GuardrailsDashboard />);

    await waitFor(() => {
      expect(mockGetGatewayAggregatedMetrics).toHaveBeenCalledWith('1h');
      expect(mockGetGuardrailsEvents).toHaveBeenCalledWith(50, '1h');
    });

    fireEvent.click(screen.getByRole('button', { name: '6h' }));

    await waitFor(() => {
      expect(mockGetGatewayAggregatedMetrics).toHaveBeenCalledWith('6h');
      expect(mockGetGuardrailsEvents).toHaveBeenCalledWith(50, '6h');
    });
  });

  it('time range selector does not refetch config', async () => {
    renderWithProviders(<GuardrailsDashboard />);

    await waitFor(() => expect(mockGetGuardrailsConfig).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '24h' }));

    await waitFor(() => expect(mockGetGatewayAggregatedMetrics).toHaveBeenCalledWith('24h'));
    expect(mockGetGuardrailsConfig).toHaveBeenCalledTimes(1);
  });

  it('rate limit card does not use a synthetic all filter', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics(
        {},
        { rate_limit: { state: 'evaluations_zero_trips', evaluations_count: 10, trips_count: 0 } }
      )
    );

    renderWithProviders(<GuardrailsDashboard />);

    await waitFor(() => {
      expect(
        within(screen.getByTestId('guardrail-card-rate-limit')).getByText(
          '0 trips after 10 evaluations'
        )
      ).toBeInTheDocument();
    });
    fireEvent.click(await screen.findByTestId('guardrail-card-rate-limit'));

    expect(await screen.findByText(/— Rate Limit/)).toBeInTheDocument();
    expect(screen.queryByText(/— All/)).not.toBeInTheDocument();
  });

  it('rate limit card filters to rate-limit or shows explicit empty state', async () => {
    mockGetGatewayAggregatedMetrics.mockResolvedValue(
      metrics(
        {},
        { rate_limit: { state: 'evaluations_zero_trips', evaluations_count: 10, trips_count: 0 } }
      )
    );
    mockGetGuardrailsEvents.mockResolvedValue({
      events: [
        {
          timestamp: '2026-05-07T10:00:00Z',
          trace_id: 'trace-pii',
          span_id: 'span-pii',
          tool: 'payment-api',
          action: 'pii-redacted',
          reason: 'Sensitive payload redacted',
        },
      ],
      total: 1,
    });

    renderWithProviders(<GuardrailsDashboard />);

    await waitFor(() => {
      expect(
        within(screen.getByTestId('guardrail-card-rate-limit')).getByText(
          '0 trips after 10 evaluations'
        )
      ).toBeInTheDocument();
    });
    fireEvent.click(await screen.findByTestId('guardrail-card-rate-limit'));

    expect(await screen.findByText('No rate-limit events')).toBeInTheDocument();
  });

  it('routes guardrail event traces through the canonical Live Calls detail path', async () => {
    mockGetGuardrailsEvents.mockResolvedValue({
      events: [
        {
          timestamp: '2026-05-07T10:00:00Z',
          trace_id: 'trace-123',
          span_id: 'span-123',
          tool: 'payment-api',
          action: 'pii-redacted',
          reason: 'Sensitive payload redacted',
        },
      ],
      total: 1,
    });

    render(
      <MemoryRouter initialEntries={['/observability/security']}>
        <Routes>
          <Route path="/observability/security" element={<GuardrailsDashboard />} />
          <Route path="/observability/live-calls/trace/:traceId" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    );

    const toolCell = await screen.findByText('payment-api');
    const eventRow = toolCell.closest('button');
    expect(eventRow).not.toBeNull();
    fireEvent.click(eventRow as HTMLButtonElement);

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/observability/live-calls/trace/trace-123'
      );
    });
  });

  it('P1-1: metrics render when events endpoint fails (allSettled)', async () => {
    mockGetGuardrailsEvents.mockRejectedValue(new Error('Events endpoint 500'));

    renderWithProviders(<GuardrailsDashboard />);

    expect(await screen.findAllByText('5 trips observed')).not.toHaveLength(0);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<GuardrailsDashboard />);
        expect(
          await screen.findByRole('heading', { name: /Security & Guardrails/i })
        ).toBeInTheDocument();
      });
    }
  );
});
