/**
 * Regression: Live Calls must use current Prometheus route labels.
 *
 * PR-2 evidence showed current stoa_http_* series expose http_route, not path.
 * The dashboard must not collapse route panels into fabricated "unknown" rows.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { usePrometheusQuery, usePrometheusRange } from '../../hooks/usePrometheus';
import { apiService } from '../../services/api';
import { CallFlowDashboard } from '../../pages/CallFlow/CallFlowDashboard';
import {
  buildLiveCallsQueries,
  HEATMAP_EMPTY_MESSAGE,
  METRICS_TRACES_SPLIT_MESSAGE,
  MODE_FILTER,
  ROUTE_LABEL,
} from '../../pages/CallFlow/metrics';

const mocks = vi.hoisted(() => ({
  getTransactions: vi.fn(),
  refetch: vi.fn(),
}));

vi.mock('../../hooks/usePrometheus', async () => {
  const actual = await vi.importActual<typeof import('../../hooks/usePrometheus')>(
    '../../hooks/usePrometheus'
  );
  return {
    ...actual,
    usePrometheusQuery: vi.fn(),
    usePrometheusRange: vi.fn(),
  };
});

vi.mock('../../services/api', () => ({
  apiService: {
    getTransactions: mocks.getTransactions,
  },
}));

function vector(value: number, metric: Record<string, string> = {}) {
  return [{ metric, value: [123, String(value)] as [number, string] }];
}

function statusVectors(values: Record<string, number>) {
  return Object.entries(values).map(([status, value]) => ({
    metric: { status },
    value: [123, String(value)] as [number, string],
  }));
}

function mockLiveCallsMetrics(totalRequests = 42, statusMix: Record<string, number> = {}) {
  vi.mocked(usePrometheusQuery).mockImplementation((query: string) => {
    if (query.startsWith('sum(increase(stoa_http_requests_total') && !query.includes('status=')) {
      return { data: vector(totalRequests), loading: false, error: null, refetch: mocks.refetch };
    }
    if (query.includes('status=~"2..|3..|4..|5.."')) {
      return {
        data: statusVectors(statusMix),
        loading: false,
        error: null,
        refetch: mocks.refetch,
      };
    }
    if (query.includes('sum by (status)') && query.includes('status=~"4.."')) {
      return {
        data: statusVectors(
          Object.fromEntries(Object.entries(statusMix).filter(([s]) => s[0] === '4'))
        ),
        loading: false,
        error: null,
        refetch: mocks.refetch,
      };
    }
    if (query.includes('sum by (status)') && query.includes('status=~"5.."')) {
      return {
        data: statusVectors(
          Object.fromEntries(Object.entries(statusMix).filter(([s]) => s[0] === '5'))
        ),
        loading: false,
        error: null,
        refetch: mocks.refetch,
      };
    }
    if (query.includes('status=~"5.."')) {
      const serverFailures = Object.entries(statusMix)
        .filter(([status]) => status[0] === '5')
        .reduce((sum, [, value]) => sum + value, 0);
      return {
        data: vector(serverFailures),
        loading: false,
        error: null,
        refetch: mocks.refetch,
      };
    }
    if (query.includes('status=~')) {
      return { data: vector(0), loading: false, error: null, refetch: mocks.refetch };
    }
    if (query.startsWith('histogram_quantile')) {
      return { data: vector(0.05), loading: false, error: null, refetch: mocks.refetch };
    }
    if (query.startsWith('count(count by (job)')) {
      return { data: vector(1), loading: false, error: null, refetch: mocks.refetch };
    }
    return { data: [], loading: false, error: null, refetch: mocks.refetch };
  });

  vi.mocked(usePrometheusRange).mockReturnValue({
    data: [],
    loading: false,
    error: null,
    refetch: mocks.refetch,
  });
  vi.mocked(apiService.getTransactions).mockResolvedValue({ transactions: [] });
}

describe('regression/live-calls-metric-integrity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLiveCallsMetrics();
  });

  it('builds route-level PromQL with http_route and the shared mode scope', () => {
    const queries = buildLiveCallsQueries('1h');
    const queryText = Object.values(queries).join('\n');

    expect(queries.topRoutesP95).toContain(`sum by (le, ${ROUTE_LABEL})`);
    expect(queries.topRoutesCalls).toContain(`sum by (${ROUTE_LABEL})`);
    expect(queries.trafficHeatmap).toContain(`sum by (${ROUTE_LABEL})`);
    expect(queries.trafficHeatmap).toContain('[1h]');
    expect(queries.activeModes).toContain('count by (job)');
    expect(queries.activeModes).not.toContain('path');
    expect(queries.errorsByStatus).toContain('status=~"5.."');
    expect(queries.errorsByStatus).not.toContain('4..');
    expect(queries.clientErrorsByStatus).toContain('status=~"4.."');
    expect(queries.statusMix).toContain('status=~"2..|3..|4..|5.."');
    expect(queryText).toContain(MODE_FILTER);
    expect(queryText).not.toMatch(/sum by \(path\)|count by \(path\)|metric\.path/);
  });

  it('separates status semantics into success mix, client errors, and 5xx failures', async () => {
    mockLiveCallsMetrics(100, { '200': 95, '302': 2, '404': 2, '500': 1 });

    renderWithProviders(<CallFlowDashboard />, { route: '/observability/live-calls' });

    expect(await screen.findByRole('heading', { name: 'Status Mix' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Failures (5xx only)' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Client errors (4xx)' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Error Breakdown' })).not.toBeInTheDocument();
    expect(screen.getByTestId('status-mix-share-2xx')).toHaveTextContent('95.0%');
  });

  it('shows a scope mismatch banner when total requests exist but mode breakdowns are empty', async () => {
    renderWithProviders(<CallFlowDashboard />, { route: '/observability/live-calls' });

    expect(
      await screen.findByText(
        /Total requests are available, but no Gateway\/Link\/Connect breakdown traffic was found/
      )
    ).toBeInTheDocument();
  });

  it('clarifies metrics and traces are separate pipelines when requests exist but traces are empty', async () => {
    renderWithProviders(<CallFlowDashboard />, { route: '/observability/live-calls' });

    expect(await screen.findByText(METRICS_TRACES_SPLIT_MESSAGE)).toBeInTheDocument();
  });

  it('renders a neutral heatmap empty state when route traffic is absent', async () => {
    renderWithProviders(<CallFlowDashboard />, { route: '/observability/live-calls' });

    expect(await screen.findByText(HEATMAP_EMPTY_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText(/traffic heatmap unavailable/i)).not.toBeInTheDocument();
  });
});
