/**
 * Regression: CAB-2224 wires the Live Calls traffic heatmap to grouped
 * Prometheus query_range data instead of the previous permanent unavailable state.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { usePrometheusQuery, usePrometheusRange } from '../../hooks/usePrometheus';
import { apiService } from '../../services/api';
import { CallFlowDashboard } from '../../pages/CallFlow/CallFlowDashboard';

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

function rangeSeries(route: string, values: number[]) {
  const base = Date.UTC(2026, 4, 13, 0, 0, 0) / 1000;
  return {
    metric: { http_route: route },
    values: values.map((value, index) => ({
      timestamp: base + index * 3600,
      value,
    })),
  };
}

function mockLiveCallsMetrics() {
  vi.mocked(usePrometheusQuery).mockImplementation((query: string) => {
    if (query.startsWith('sum(increase(stoa_http_requests_total') && !query.includes('status=')) {
      return { data: vector(96), loading: false, error: null, refetch: mocks.refetch };
    }
    if (query.startsWith('histogram_quantile')) {
      return { data: vector(0.05), loading: false, error: null, refetch: mocks.refetch };
    }
    if (query.startsWith('count(count by (job)')) {
      return { data: vector(1), loading: false, error: null, refetch: mocks.refetch };
    }
    return { data: [], loading: false, error: null, refetch: mocks.refetch };
  });

  vi.mocked(usePrometheusRange).mockImplementation((query: string) => {
    if (query.includes('sum by (http_route)') && query.includes('[1h]')) {
      const series = [
        rangeSeries('/customers/{id}', [0, 5, 8, 12]),
        rangeSeries('/orders', [0, 2, 4, 6]),
        rangeSeries('/quiet', [0, 0, 0, 0]),
      ];
      return {
        data: series[0].values,
        series,
        loading: false,
        error: null,
        refetch: mocks.refetch,
      };
    }
    return { data: [], series: [], loading: false, error: null, refetch: mocks.refetch };
  });

  vi.mocked(apiService.getTransactions).mockResolvedValue({ transactions: [] });
}

describe('regression/CAB-2224 live-calls heatmap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLiveCallsMetrics();
  });

  it('renders grouped http_route query_range buckets as traffic heatmap rows', async () => {
    renderWithProviders(<CallFlowDashboard />, { route: '/observability/live-calls' });

    expect(await screen.findByTestId('traffic-heatmap')).toBeInTheDocument();
    expect(screen.getByText('/customers/{id}')).toBeInTheDocument();
    expect(screen.getByText('/orders')).toBeInTheDocument();
    expect(screen.queryByText(/traffic heatmap unavailable/i)).not.toBeInTheDocument();
    expect(usePrometheusRange).toHaveBeenCalledWith(
      expect.stringContaining('sum by (http_route)'),
      86_400,
      '3600',
      15_000
    );
  });
});
