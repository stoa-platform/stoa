import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProxyOwnerDashboard } from './ProxyOwnerDashboard';
import { createAuthMock, renderWithProviders, type PersonaRole } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  apiService: { get: vi.fn() },
}));

vi.mock('../../config', () => ({
  config: { services: { grafana: { url: '' } } },
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

const mockGatewayInstances = [
  {
    id: 'gw-1',
    name: 'stoa-edge-mcp-1',
    display_name: 'STOA Edge MCP',
    status: 'online',
    base_url: 'https://mcp.gostoa.dev',
  },
  {
    id: 'gw-2',
    name: 'kong-standalone',
    display_name: 'Kong DB-less',
    status: 'online',
    base_url: 'https://kong.gostoa.dev',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiService.get).mockResolvedValue({
    data: { items: mockGatewayInstances },
  });
});

describe('ProxyOwnerDashboard', () => {
  describe('loading state', () => {
    it('shows skeleton cards while loading', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      // Never resolve to keep loading state
      vi.mocked(apiService.get).mockReturnValue(new Promise(() => {}));

      renderWithProviders(<ProxyOwnerDashboard />);

      expect(screen.getAllByTestId('card-skeleton')).toHaveLength(4);
    });
  });

  describe('loaded state (cpi-admin)', () => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    });

    it('renders the page title', async () => {
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Proxy Owner Dashboard')).toBeInTheDocument();
      });
    });

    it('renders KPI cards after data loads', async () => {
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateways Online')).toBeInTheDocument();
      });
      expect(screen.getAllByText('Active Policies').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Requests (24h)').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Violations (24h)').length).toBeGreaterThanOrEqual(1);
    });

    it('renders gateway instances table', async () => {
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Instances')).toBeInTheDocument();
      });
      expect(screen.getByText('STOA Edge MCP')).toBeInTheDocument();
      expect(screen.getByText('Kong DB-less')).toBeInTheDocument();
    });

    it('renders cross-tenant traffic section (admin-only)', async () => {
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Cross-Tenant Traffic')).toBeInTheDocument();
      });
      expect(screen.getByText('Unique Tenants')).toBeInTheDocument();
      expect(screen.getByText('Cross-Tenant Calls')).toBeInTheDocument();
    });

    it('renders policy enforcement section', async () => {
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Policy Enforcement')).toBeInTheDocument();
      });
      // 'Active Policies' appears in both KPI cards and Policy Enforcement section
      expect(screen.getAllByText('Active Policies').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Enforced Today')).toBeInTheDocument();
    });

    it('has a refresh button', async () => {
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Proxy Owner Dashboard')).toBeInTheDocument();
      });

      const refreshBtn = screen.getByRole('button', { name: /refresh dashboard/i });
      expect(refreshBtn).toBeInTheDocument();
    });

    it('calls API on refresh click', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Proxy Owner Dashboard')).toBeInTheDocument();
      });

      // Initial load + auto-refresh may have called already
      const initialCalls = vi.mocked(apiService.get).mock.calls.length;

      const refreshBtn = screen.getByRole('button', { name: /refresh dashboard/i });
      await user.click(refreshBtn);

      expect(vi.mocked(apiService.get).mock.calls.length).toBeGreaterThan(initialCalls);
    });

    it('does not show the non-admin info banner', async () => {
      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Proxy Owner Dashboard')).toBeInTheDocument();
      });

      expect(
        screen.queryByText(/contact a platform admin for cross-tenant metrics/i)
      ).not.toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows error banner when API fails', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      vi.mocked(apiService.get).mockRejectedValue(new Error('Network error'));

      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });
  });

  describe('empty state', () => {
    it('shows empty message when no gateways', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      vi.mocked(apiService.get).mockResolvedValue({ data: { items: [] } });

      renderWithProviders(<ProxyOwnerDashboard />);

      await waitFor(() => {
        expect(screen.getByText('No gateway instances registered')).toBeInTheDocument();
      });
    });
  });

  describe.each<PersonaRole>(['tenant-admin', 'devops', 'viewer'])(
    'non-admin persona: %s',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      });

      it('hides cross-tenant traffic section', async () => {
        renderWithProviders(<ProxyOwnerDashboard />);

        await waitFor(() => {
          expect(screen.getByText('Proxy Owner Dashboard')).toBeInTheDocument();
        });

        expect(screen.queryByText('Cross-Tenant Traffic')).not.toBeInTheDocument();
      });

      it('shows non-admin info banner', async () => {
        renderWithProviders(<ProxyOwnerDashboard />);

        await waitFor(() => {
          expect(
            screen.getByText(/contact a platform admin for cross-tenant metrics/i)
          ).toBeInTheDocument();
        });
      });

      it('shows Grafana fallback message instead of iframe', async () => {
        renderWithProviders(<ProxyOwnerDashboard />);

        await waitFor(() => {
          expect(
            screen.getByText(/infrastructure metrics require platform admin access/i)
          ).toBeInTheDocument();
        });
      });

      it('still shows gateway table and KPIs', async () => {
        renderWithProviders(<ProxyOwnerDashboard />);

        await waitFor(() => {
          expect(screen.getByText('Gateway Instances')).toBeInTheDocument();
        });
        expect(screen.getByText('Gateways Online')).toBeInTheDocument();
        expect(screen.getByText('Policy Enforcement')).toBeInTheDocument();
      });
    }
  );
});
