import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { CallFlowDashboard } from './CallFlowDashboard';

const prometheusMocks = vi.hoisted(() => ({
  refetch: vi.fn(),
}));

vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: prometheusMocks.refetch,
  })),
  usePrometheusRange: vi.fn(() => ({
    data: [],
    loading: false,
    error: null,
    refetch: prometheusMocks.refetch,
  })),
  scalarValue: vi.fn(() => null),
  groupByLabel: vi.fn(() => ({})),
}));

vi.mock('../../services/api', () => ({
  apiService: {
    getTransactions: vi.fn().mockResolvedValue({ transactions: [] }),
  },
}));

describe('CallFlowDashboard', () => {
  it('renders the Live Calls product heading', async () => {
    renderWithProviders(<CallFlowDashboard />, { route: '/observability/live-calls' });

    expect(await screen.findByRole('heading', { name: 'Live Calls' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Call Flow' })).not.toBeInTheDocument();
  });
});
