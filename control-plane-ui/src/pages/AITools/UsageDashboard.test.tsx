import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockUsageData = {
  period: 'week',
  startDate: '2026-02-03',
  endDate: '2026-02-10',
  totalCalls: 156,
  successRate: 0.98,
  totalCostUnits: 0.023,
  avgLatencyMs: 145,
  toolBreakdown: [],
};

const mockGetMyUsage = vi.fn().mockResolvedValue(mockUsageData);
const mockGetUsageHistory = vi.fn().mockResolvedValue({ dataPoints: [] });

vi.mock('../../services/mcpGatewayApi', () => ({
  mcpGatewayService: {
    getMyUsage: (...args: unknown[]) => mockGetMyUsage(...args),
    getUsageHistory: (...args: unknown[]) => mockGetUsageHistory(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('../../components/tools', () => ({
  UsageChart: ({ title }: { title?: string }) => <div data-testid="usage-chart">{title}</div>,
  UsageStatsCard: ({ title }: { title?: string }) => (
    <div data-testid="usage-stats-card">{title}</div>
  ),
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { UsageDashboard } from './UsageDashboard';

describe('UsageDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetMyUsage.mockResolvedValue(mockUsageData);
    mockGetUsageHistory.mockResolvedValue({ dataPoints: [] });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderWithProviders(<UsageDashboard />);
    expect(await screen.findByRole('heading', { name: /Usage Dashboard/ })).toBeInTheDocument();
  });

  it('renders period selector with default option', async () => {
    renderWithProviders(<UsageDashboard />);
    expect(await screen.findByText('Last 7 days')).toBeInTheDocument();
  });

  it('renders stats cards', async () => {
    renderWithProviders(<UsageDashboard />);
    await waitFor(() => {
      expect(screen.getAllByTestId('usage-stats-card').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows error message on API failure', async () => {
    mockGetMyUsage.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<UsageDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/failed|error/i)).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<UsageDashboard />);
        expect(await screen.findByRole('heading', { name: /Usage Dashboard/ })).toBeInTheDocument();
      });
    }
  );
});
