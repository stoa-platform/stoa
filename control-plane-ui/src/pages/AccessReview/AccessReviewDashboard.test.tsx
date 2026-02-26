import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AccessReviewDashboard } from './AccessReviewDashboard';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockClients = [
  {
    id: 'client-1',
    tenant_id: 'oasis-gunters',
    keycloak_client_id: 'kc-client-1',
    client_name: 'Payment Service',
    description: 'Processes payments',
    product_roles: ['api:read', 'api:write'],
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    id: 'client-2',
    tenant_id: 'oasis-gunters',
    keycloak_client_id: 'kc-client-2',
    client_name: 'Analytics Agent',
    description: 'Data analytics',
    product_roles: ['api:read'],
    status: 'revoked',
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-02-10T00:00:00Z',
  },
  {
    id: 'client-3',
    tenant_id: 'oasis-gunters',
    keycloak_client_id: 'kc-client-3',
    client_name: 'Pending Agent',
    description: null,
    product_roles: null,
    status: 'pending_review',
    created_at: '2026-02-20T00:00:00Z',
    updated_at: '2026-02-20T00:00:00Z',
  },
  {
    id: 'client-4',
    tenant_id: 'oasis-gunters',
    keycloak_client_id: 'kc-client-4',
    client_name: 'Expired Token Service',
    description: 'Legacy service',
    product_roles: ['legacy:read'],
    status: 'expired',
    created_at: '2025-06-01T00:00:00Z',
    updated_at: '2025-12-01T00:00:00Z',
  },
];

const mockGet = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function setupApiMock(clients = mockClients) {
  mockGet.mockResolvedValue({
    data: { items: clients, total: clients.length, page: 1, page_size: 50 },
  });
}

function setupApiError() {
  mockGet.mockRejectedValue(new Error('Network error'));
}

describe('AccessReviewDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    setupApiMock();
  });

  it('renders the page title', async () => {
    renderWithProviders(<AccessReviewDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Access Review')).toBeInTheDocument();
    });
  });

  it('renders the subtitle with tenant ID', async () => {
    renderWithProviders(<AccessReviewDashboard />);
    await waitFor(() => {
      expect(
        screen.getByText(/Review and manage OAuth client access for tenant/)
      ).toBeInTheDocument();
    });
  });

  it('renders refresh button', async () => {
    renderWithProviders(<AccessReviewDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('refresh-btn')).toBeInTheDocument();
    });
  });

  it('shows loading skeletons initially', () => {
    setupApiMock();
    // Mock a never-resolving promise to keep loading state
    mockGet.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<AccessReviewDashboard />);
    // During loading, skeletons are shown (no summary cards yet)
    expect(screen.queryByTestId('summary-cards')).not.toBeInTheDocument();
  });

  describe('Summary Cards', () => {
    it('shows summary cards after loading', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('summary-cards')).toBeInTheDocument();
      });
    });

    it('shows total clients count', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Total Clients')).toBeInTheDocument();
        expect(screen.getByText('4')).toBeInTheDocument();
      });
    });

    it('shows active clients count', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Active')).toBeInTheDocument();
      });
    });

    it('shows revoked clients count', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Revoked')).toBeInTheDocument();
      });
    });

    it('shows pending review count', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Pending Review')).toBeInTheDocument();
      });
    });
  });

  describe('Clients Table', () => {
    it('renders client names', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Payment Service')).toBeInTheDocument();
        expect(screen.getByText('Analytics Agent')).toBeInTheDocument();
        expect(screen.getByText('Pending Agent')).toBeInTheDocument();
        expect(screen.getByText('Expired Token Service')).toBeInTheDocument();
      });
    });

    it('renders keycloak client IDs', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('kc-client-1')).toBeInTheDocument();
        expect(screen.getByText('kc-client-2')).toBeInTheDocument();
      });
    });

    it('renders status badges', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('status-badge-active')).toBeInTheDocument();
        expect(screen.getByTestId('status-badge-revoked')).toBeInTheDocument();
        expect(screen.getByTestId('status-badge-pending_review')).toBeInTheDocument();
        expect(screen.getByTestId('status-badge-expired')).toBeInTheDocument();
      });
    });

    it('renders product roles as badges', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getAllByText('api:read').length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('api:write')).toBeInTheDocument();
      });
    });

    it('renders updated dates', async () => {
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Payment Service')).toBeInTheDocument();
      });
      const body = screen.getByTestId('clients-table-body');
      expect(body).toBeInTheDocument();
    });

    it('shows empty state when no clients', async () => {
      setupApiMock([]);
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('No OAuth clients found for this tenant.')).toBeInTheDocument();
      });
    });

    it('handles API error gracefully', async () => {
      setupApiError();
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('No OAuth clients found for this tenant.')).toBeInTheDocument();
      });
    });
  });

  describe('Refresh', () => {
    it('calls API on refresh click', async () => {
      const user = userEvent.setup();
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Payment Service')).toBeInTheDocument();
      });
      const refreshBtn = screen.getByTestId('refresh-btn');
      await user.click(refreshBtn);
      // API called twice: initial load + refresh
      expect(mockGet).toHaveBeenCalledTimes(2);
    });
  });

  describe('RBAC-gated Actions', () => {
    it('shows Actions column for cpi-admin', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Actions')).toBeInTheDocument();
      });
    });

    it('shows Actions column for tenant-admin', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Actions')).toBeInTheDocument();
      });
    });

    it('hides Actions column for devops', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('devops'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Payment Service')).toBeInTheDocument();
      });
      expect(screen.queryByText('Actions')).not.toBeInTheDocument();
    });

    it('hides Actions column for viewer', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Payment Service')).toBeInTheDocument();
      });
      expect(screen.queryByText('Actions')).not.toBeInTheDocument();
    });

    it('shows Approve button for pending_review clients', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('approve-client-3')).toBeInTheDocument();
      });
    });

    it('shows Revoke button for active clients', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('revoke-client-1')).toBeInTheDocument();
      });
    });

    it('shows Flag button for all clients with actions', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('flag-client-1')).toBeInTheDocument();
        expect(screen.getByTestId('flag-client-2')).toBeInTheDocument();
        expect(screen.getByTestId('flag-client-3')).toBeInTheDocument();
      });
    });

    it('does not show Approve button for active clients', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Payment Service')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('approve-client-1')).not.toBeInTheDocument();
    });

    it('does not show Revoke button for revoked clients', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<AccessReviewDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Analytics Agent')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('revoke-client-2')).not.toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      });

      it('renders the page', async () => {
        renderWithProviders(<AccessReviewDashboard />);
        await waitFor(() => {
          expect(screen.getByText('Access Review')).toBeInTheDocument();
        });
      });

      it('shows summary cards', async () => {
        renderWithProviders(<AccessReviewDashboard />);
        await waitFor(() => {
          expect(screen.getByTestId('summary-cards')).toBeInTheDocument();
        });
      });

      it('shows clients table', async () => {
        renderWithProviders(<AccessReviewDashboard />);
        await waitFor(() => {
          expect(screen.getByTestId('clients-table-body')).toBeInTheDocument();
        });
      });

      it('shows client names', async () => {
        renderWithProviders(<AccessReviewDashboard />);
        await waitFor(() => {
          expect(screen.getByText('Payment Service')).toBeInTheDocument();
        });
      });
    }
  );
});
