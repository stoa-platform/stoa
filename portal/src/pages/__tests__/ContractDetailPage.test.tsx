/**
 * ContractDetailPage Tests - CAB-1133
 *
 * Tests for the contract detail view with protocol switcher.
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { ContractDetailPage } from '../contracts/ContractDetailPage';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock useParams
const mockParams = { id: 'contract-1' };
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => mockParams,
    useNavigate: () => vi.fn(),
  };
});

// Mock useContract hook
const mockUseContract = vi.fn();

vi.mock('../../hooks/useContracts', () => ({
  useContract: (id: string) => mockUseContract(id),
}));

// Mock ProtocolSwitcher component
vi.mock('../../components/contracts', () => ({
  ProtocolSwitcher: ({
    contractId,
  }: {
    contractId: string;
    onBindingEnabled: () => void;
    onBindingDisabled: () => void;
  }) => <div data-testid="protocol-switcher">Protocol Switcher for {contractId}</div>,
}));

// Mock UACBadge component
vi.mock('../../components/uac', () => ({
  UACBadge: ({ contractName }: { contractName: string }) => (
    <div data-testid="uac-badge">UAC: {contractName}</div>
  ),
}));

// Mock formatRelativeTime
vi.mock('../../utils/format', () => ({
  formatRelativeTime: (date: string) => `relative: ${date}`,
}));

describe('ContractDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('renders loading state', async () => {
    mockUseContract.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });

    const { container } = renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      const spinner = container.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });
  });

  it('renders error state', async () => {
    mockUseContract.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
    });

    renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load contract')).toBeInTheDocument();
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('renders not found state when contract is null', async () => {
    mockUseContract.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('Contract not found')).toBeInTheDocument();
    });
  });

  it('renders contract metadata (name, version, status)', async () => {
    mockUseContract.mockReturnValue({
      data: {
        id: 'contract-1',
        tenant_id: 'oasis-gunters',
        name: 'orders-api',
        display_name: 'Orders API',
        description: 'Order management service',
        version: '1.0.0',
        status: 'published',
        openapi_spec_url: 'https://api.example.com/openapi.json',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-02-01T00:00:00Z',
        created_by: 'user-parzival',
        bindings: [
          { protocol: 'rest', enabled: true, endpoint: '/v1/orders' },
          { protocol: 'mcp', enabled: true, tool_name: 'orders-api' },
        ],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('Orders API')).toBeInTheDocument();
      expect(screen.getByText('v1.0.0')).toBeInTheDocument();
      expect(screen.getByText('published')).toBeInTheDocument();
      expect(screen.getByText('Order management service')).toBeInTheDocument();
    });
  });

  it('renders Protocol Switcher component', async () => {
    mockUseContract.mockReturnValue({
      data: {
        id: 'contract-1',
        tenant_id: 'oasis-gunters',
        name: 'orders-api',
        display_name: 'Orders API',
        description: 'Order management service',
        version: '1.0.0',
        status: 'published',
        openapi_spec_url: 'https://api.example.com/openapi.json',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-02-01T00:00:00Z',
        created_by: 'user-parzival',
        bindings: [
          { protocol: 'rest', enabled: true, endpoint: '/v1/orders' },
          { protocol: 'mcp', enabled: true, tool_name: 'orders-api' },
        ],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId('protocol-switcher')).toBeInTheDocument();
      expect(screen.getByText(/Protocol Switcher for contract-1/)).toBeInTheDocument();
    });
  });

  it('renders Quick Access section with enabled bindings', async () => {
    mockUseContract.mockReturnValue({
      data: {
        id: 'contract-1',
        tenant_id: 'oasis-gunters',
        name: 'orders-api',
        display_name: 'Orders API',
        description: 'Order management service',
        version: '1.0.0',
        status: 'published',
        openapi_spec_url: 'https://api.example.com/openapi.json',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-02-01T00:00:00Z',
        created_by: 'user-parzival',
        bindings: [
          { protocol: 'rest', enabled: true, endpoint: '/v1/orders' },
          { protocol: 'mcp', enabled: true, tool_name: 'orders-api' },
        ],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('Quick Access')).toBeInTheDocument();
      expect(screen.getByText('REST API')).toBeInTheDocument();
      expect(screen.getByText('MCP Tool')).toBeInTheDocument();
    });
  });

  it('renders OpenAPI Spec section when URL is present', async () => {
    mockUseContract.mockReturnValue({
      data: {
        id: 'contract-1',
        tenant_id: 'oasis-gunters',
        name: 'orders-api',
        display_name: 'Orders API',
        description: 'Order management service',
        version: '1.0.0',
        status: 'published',
        openapi_spec_url: 'https://api.example.com/openapi.json',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-02-01T00:00:00Z',
        created_by: 'user-parzival',
        bindings: [],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('OpenAPI Spec')).toBeInTheDocument();
      expect(screen.getByText('https://api.example.com/openapi.json')).toBeInTheDocument();
    });
  });

  it('shows message when no bindings are enabled', async () => {
    mockUseContract.mockReturnValue({
      data: {
        id: 'contract-1',
        tenant_id: 'oasis-gunters',
        name: 'orders-api',
        display_name: 'Orders API',
        description: 'Order management service',
        version: '1.0.0',
        status: 'published',
        openapi_spec_url: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-02-01T00:00:00Z',
        created_by: 'user-parzival',
        bindings: [
          { protocol: 'rest', enabled: false, endpoint: '/v1/orders' },
          { protocol: 'mcp', enabled: false, tool_name: 'orders-api' },
        ],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractDetailPage />);

    await waitFor(() => {
      expect(
        screen.getByText('Enable protocol bindings to access your API endpoints.')
      ).toBeInTheDocument();
    });
  });
});
