import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { GatewaysPage } from '../gateways/GatewaysPage';

// Mock gatewaysService
const mockListGateways = vi.fn();
vi.mock('../../services/gateways', () => ({
  gatewaysService: {
    listGateways: (...args: unknown[]) => mockListGateways(...args),
    triggerHealthCheck: vi.fn().mockResolvedValue(true),
  },
}));

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    user: { id: '1', roles: ['cpi-admin'], permissions: [], effective_scopes: [] },
    hasPermission: () => true,
    hasRole: () => true,
    hasScope: () => true,
    hasAnyPermission: () => true,
    hasAllPermissions: () => true,
  }),
}));

describe('GatewaysPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders table when gateways exist', async () => {
    mockListGateways.mockResolvedValue({
      items: [
        {
          id: '1',
          name: 'kong-gra',
          display_name: 'Kong DB-less (GRA)',
          gateway_type: 'kong',
          base_url: 'https://kong.example.com',
          environment: 'prod',
          status: 'online',
          last_health_check: '2026-02-12T10:00:00Z',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-02-12T10:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderWithProviders(<GatewaysPage />);

    await waitFor(() => {
      expect(screen.getByText('Kong DB-less (GRA)')).toBeInTheDocument();
    });
    expect(screen.getByText('Online')).toBeInTheDocument();
  });

  it('renders empty state when no gateways', async () => {
    mockListGateways.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });

    renderWithProviders(<GatewaysPage />);

    await waitFor(() => {
      expect(screen.getByText('No gateways registered')).toBeInTheDocument();
    });
  });
});
