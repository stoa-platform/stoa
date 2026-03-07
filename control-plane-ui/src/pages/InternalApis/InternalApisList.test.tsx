import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InternalApisList } from './InternalApisList';
import { createAuthMock, renderWithProviders, type PersonaRole } from '../../test/helpers';
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

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

const mockList = vi.mocked(proxyBackendService.list);
const mockHealthCheck = vi.mocked(proxyBackendService.healthCheck);

const mockBackends = [
  {
    id: 'pb-1',
    name: 'n8n',
    display_name: 'n8n Workflow Automation',
    description: null,
    base_url: 'https://n8n.gostoa.dev',
    health_endpoint: '/healthz',
    auth_type: 'api_key' as const,
    credential_ref: 'api-proxy:n8n',
    rate_limit_rpm: 60,
    circuit_breaker_enabled: true,
    fallback_direct: false,
    timeout_secs: 30,
    status: 'active' as const,
    is_active: true,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
  },
  {
    id: 'pb-2',
    name: 'linear',
    display_name: 'Linear',
    description: null,
    base_url: 'https://api.linear.app',
    health_endpoint: '/graphql',
    auth_type: 'bearer' as const,
    credential_ref: 'api-proxy:linear',
    rate_limit_rpm: 120,
    circuit_breaker_enabled: true,
    fallback_direct: false,
    timeout_secs: 30,
    status: 'active' as const,
    is_active: true,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
  },
  {
    id: 'pb-3',
    name: 'slack-bot',
    display_name: 'Slack Bot',
    description: null,
    base_url: 'https://slack.com/api',
    health_endpoint: null,
    auth_type: 'bearer' as const,
    credential_ref: 'api-proxy:slack-bot',
    rate_limit_rpm: 0,
    circuit_breaker_enabled: false,
    fallback_direct: false,
    timeout_secs: 15,
    status: 'disabled' as const,
    is_active: false,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
  },
];

function setupAuth(role: PersonaRole) {
  vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
}

describe('InternalApisList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: mockBackends, total: 3 });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])('as %s', (role) => {
    beforeEach(() => {
      setupAuth(role);
    });

    it('renders the refresh button', async () => {
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });
      await waitFor(() => {
        expect(screen.getByText('Refresh')).toBeInTheDocument();
      });
    });

    it('displays backend list', async () => {
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });
      await waitFor(() => {
        expect(screen.getByText('n8n Workflow Automation')).toBeInTheDocument();
        expect(screen.getByText('Linear')).toBeInTheDocument();
        expect(screen.getByText('Slack Bot')).toBeInTheDocument();
      });
    });

    it('shows summary cards', async () => {
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });
      await waitFor(() => {
        expect(screen.getByText('Total backends')).toBeInTheDocument();
        expect(screen.getByText('3')).toBeInTheDocument();
      });
    });
  });

  describe('data display', () => {
    beforeEach(() => {
      setupAuth('cpi-admin');
    });

    it('shows rate limit values', async () => {
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });
      await waitFor(() => {
        expect(screen.getByText('60 rpm')).toBeInTheDocument();
        expect(screen.getByText('120 rpm')).toBeInTheDocument();
        expect(screen.getByText('Unlimited')).toBeInTheDocument();
      });
    });

    it('shows circuit breaker status', async () => {
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });
      await waitFor(() => {
        const enabled = screen.getAllByText('Enabled');
        expect(enabled).toHaveLength(2);
        expect(screen.getByText('Off')).toBeInTheDocument();
      });
    });

    it('shows backend status badges', async () => {
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });
      await waitFor(() => {
        const active = screen.getAllByText('Active');
        // 2 table badges + 1 summary card label + 1 select option
        expect(active.length).toBeGreaterThanOrEqual(2);
        // "Disabled" appears as both badge and select option
        const disabled = screen.getAllByText('Disabled');
        expect(disabled.length).toBeGreaterThanOrEqual(2);
      });
    });

    it('shows auth type labels', async () => {
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });
      await waitFor(() => {
        expect(screen.getByText('API Key')).toBeInTheDocument();
        const bearerCells = screen.getAllByText('Bearer');
        expect(bearerCells).toHaveLength(2);
      });
    });
  });

  describe('filtering', () => {
    beforeEach(() => {
      setupAuth('cpi-admin');
    });

    it('filters by search term', async () => {
      const user = userEvent.setup();
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });

      await waitFor(() => {
        expect(screen.getByText('n8n Workflow Automation')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText('Search backends...');
      await user.type(searchInput, 'linear');

      expect(screen.queryByText('n8n Workflow Automation')).not.toBeInTheDocument();
      expect(screen.getByText('Linear')).toBeInTheDocument();
    });

    it('filters by status', async () => {
      const user = userEvent.setup();
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });

      await waitFor(() => {
        expect(screen.getByText('Slack Bot')).toBeInTheDocument();
      });

      const select = screen.getByDisplayValue('All statuses');
      await user.selectOptions(select, 'disabled');

      expect(screen.queryByText('n8n Workflow Automation')).not.toBeInTheDocument();
      expect(screen.getByText('Slack Bot')).toBeInTheDocument();
    });
  });

  describe('health check', () => {
    beforeEach(() => {
      setupAuth('cpi-admin');
    });

    it('triggers health check on button click', async () => {
      mockHealthCheck.mockResolvedValue({
        backend_name: 'n8n',
        healthy: true,
        status_code: 200,
        latency_ms: 42,
        error: null,
        checked_at: '2026-03-06T10:00:00Z',
      });

      const user = userEvent.setup();
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });

      await waitFor(() => {
        expect(screen.getByText('n8n Workflow Automation')).toBeInTheDocument();
      });

      const checkButtons = screen.getAllByText('Check');
      await user.click(checkButtons[0]);

      await waitFor(() => {
        expect(mockHealthCheck).toHaveBeenCalledWith('pb-1');
        expect(screen.getByText('42ms')).toBeInTheDocument();
      });
    });
  });

  describe('error handling', () => {
    beforeEach(() => {
      setupAuth('cpi-admin');
    });

    it('shows error message on API failure', async () => {
      mockList.mockRejectedValue(new Error('Network error'));
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });
  });

  describe('empty state', () => {
    beforeEach(() => {
      setupAuth('cpi-admin');
    });

    it('shows empty state when no backends', async () => {
      mockList.mockResolvedValue({ items: [], total: 0 });
      renderWithProviders(<InternalApisList />, { route: '/internal-apis' });

      await waitFor(() => {
        expect(screen.getByText('No internal APIs registered')).toBeInTheDocument();
      });
    });
  });
});
