import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { ApiTrafficDashboard } from './ApiTrafficDashboard';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { proxyBackendService } from '../../services/proxyBackendService';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../services/proxyBackendService', () => ({
  proxyBackendService: {
    list: vi.fn(),
    healthCheck: vi.fn(),
  },
}));

vi.mock('../../config', () => ({
  config: { services: { grafana: { url: '/grafana/' } } },
}));

const mockBackends = {
  items: [
    {
      id: 'pb-1',
      name: 'linear',
      display_name: 'Linear Issue Tracker',
      description: null,
      base_url: 'https://api.linear.app',
      health_endpoint: null,
      auth_type: 'bearer' as const,
      credential_ref: 'api-proxy:linear',
      rate_limit_rpm: 1500,
      circuit_breaker_enabled: true,
      fallback_direct: true,
      timeout_secs: 30,
      status: 'active' as const,
      is_active: true,
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
    },
    {
      id: 'pb-2',
      name: 'github',
      display_name: 'GitHub API',
      description: null,
      base_url: 'https://api.github.com',
      health_endpoint: null,
      auth_type: 'bearer' as const,
      credential_ref: 'api-proxy:github',
      rate_limit_rpm: 5000,
      circuit_breaker_enabled: true,
      fallback_direct: true,
      timeout_secs: 30,
      status: 'active' as const,
      is_active: true,
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
    },
  ],
  total: 2,
};

const mockHealth = {
  backend_name: 'linear',
  healthy: true,
  status_code: 200,
  latency_ms: 45,
  error: null,
  checked_at: '2026-03-06T12:00:00Z',
};

describe('ApiTrafficDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.mocked(proxyBackendService.list).mockResolvedValue(mockBackends);
    vi.mocked(proxyBackendService.healthCheck).mockResolvedValue(mockHealth);
  });

  it('renders dashboard with backend table', async () => {
    renderWithProviders(<ApiTrafficDashboard />, { route: '/api-traffic' });

    await waitFor(() => {
      expect(screen.getByText('API Traffic')).toBeInTheDocument();
    });

    expect(screen.getByText('Linear Issue Tracker')).toBeInTheDocument();
    expect(screen.getByText('GitHub API')).toBeInTheDocument();
  });

  it('shows KPI cards with correct counts', async () => {
    renderWithProviders(<ApiTrafficDashboard />, { route: '/api-traffic' });

    await waitFor(() => {
      expect(screen.getByText('Active Backends')).toBeInTheDocument();
    });

    expect(screen.getAllByText('2/2').length).toBeGreaterThan(0);
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('Circuit Breakers')).toBeInTheDocument();
  });

  it('shows rate limit info per backend', async () => {
    renderWithProviders(<ApiTrafficDashboard />, { route: '/api-traffic' });

    await waitFor(() => {
      expect(screen.getByText('1.5K/min')).toBeInTheDocument();
    });

    expect(screen.getByText('5.0K/min')).toBeInTheDocument();
  });

  it('shows empty state when no backends', async () => {
    vi.mocked(proxyBackendService.list).mockResolvedValue({ items: [], total: 0 });

    renderWithProviders(<ApiTrafficDashboard />, { route: '/api-traffic' });

    await waitFor(() => {
      expect(screen.getByText(/No proxy backends registered/)).toBeInTheDocument();
    });
  });

  it('shows error banner on API failure', async () => {
    vi.mocked(proxyBackendService.list).mockRejectedValue(new Error('Network error'));

    renderWithProviders(<ApiTrafficDashboard />, { route: '/api-traffic' });

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('shows circuit breaker alert when unhealthy backend has CB enabled', async () => {
    vi.mocked(proxyBackendService.healthCheck).mockResolvedValue({
      ...mockHealth,
      healthy: false,
      error: 'Connection refused',
    });

    renderWithProviders(<ApiTrafficDashboard />, { route: '/api-traffic' });

    await waitFor(() => {
      expect(screen.getByText('Circuit breaker may be open')).toBeInTheDocument();
    });
  });
});
