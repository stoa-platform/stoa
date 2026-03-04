import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { HegemonDashboard } from './HegemonDashboard';
import { renderWithProviders, createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../services/api', () => ({
  apiService: {
    getAiSessionStats: vi.fn(),
    getTraces: vi.fn(),
  },
}));

const mockStats = {
  days: 7,
  totals: {
    sessions: 12,
    total_duration_ms: 7_200_000,
    avg_duration_ms: 600_000,
    success_count: 10,
    success_rate: 83,
  },
  workers: [
    {
      worker: 'hegemon-backend',
      sessions: 5,
      total_duration_ms: 3_000_000,
      avg_duration_ms: 600_000,
      success_count: 4,
      success_rate: 80,
      last_activity: new Date().toISOString(),
    },
    {
      worker: 'hegemon-frontend',
      sessions: 7,
      total_duration_ms: 4_200_000,
      avg_duration_ms: 600_000,
      success_count: 6,
      success_rate: 86,
      last_activity: null,
    },
  ],
  daily: [{ date: '2026-03-04', sessions: 3 }],
};

const mockTraces = {
  traces: [
    {
      id: 'trace-001',
      api_name: 'CAB-1528',
      trigger_type: 'ai-session',
      status: 'success',
      total_duration_ms: 900_000,
      tenant_id: 'hegemon',
      created_at: new Date().toISOString(),
    },
  ],
  total: 1,
};

describe('HegemonDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.mocked(apiService.getAiSessionStats).mockResolvedValue(mockStats);
    vi.mocked(apiService.getTraces).mockResolvedValue(mockTraces);
  });

  it('renders dashboard with stats and workers', async () => {
    renderWithProviders(<HegemonDashboard />, { route: '/hegemon' });

    await waitFor(() => {
      expect(screen.getByText('AI Factory')).toBeInTheDocument();
    });

    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('83%')).toBeInTheDocument();
    expect(screen.getByText('hegemon-backend')).toBeInTheDocument();
    expect(screen.getByText('hegemon-frontend')).toBeInTheDocument();
  });

  it('renders session list', async () => {
    renderWithProviders(<HegemonDashboard />, { route: '/hegemon' });

    await waitFor(() => {
      expect(screen.getByText('CAB-1528')).toBeInTheDocument();
    });
  });

  it('shows permission denied for viewer role', () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
    renderWithProviders(<HegemonDashboard />, { route: '/hegemon' });

    expect(screen.getByText('You do not have permission to view this page.')).toBeInTheDocument();
  });

  it('shows empty state when no sessions', async () => {
    vi.mocked(apiService.getAiSessionStats).mockResolvedValue({
      ...mockStats,
      totals: { ...mockStats.totals, sessions: 0 },
      workers: [],
    });
    vi.mocked(apiService.getTraces).mockResolvedValue({ traces: [], total: 0 });

    renderWithProviders(<HegemonDashboard />, { route: '/hegemon' });

    await waitFor(() => {
      expect(screen.getByText('No AI sessions recorded yet.')).toBeInTheDocument();
    });
  });
});
