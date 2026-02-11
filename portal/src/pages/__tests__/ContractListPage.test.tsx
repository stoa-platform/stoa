/**
 * ContractListPage Tests - CAB-1133
 *
 * Tests for the contract listing page.
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { ContractListPage } from '../contracts/ContractListPage';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock useContracts hook
const mockUseContracts = vi.fn();

vi.mock('../../hooks/useContracts', () => ({
  useContracts: () => mockUseContracts(),
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

describe('ContractListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('renders loading state', async () => {
    mockUseContracts.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });

    const { container } = renderWithProviders(<ContractListPage />);

    await waitFor(() => {
      const spinner = container.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });
  });

  it('renders error state', async () => {
    mockUseContracts.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network failure'),
    });

    renderWithProviders(<ContractListPage />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load contracts')).toBeInTheDocument();
      expect(screen.getByText('Network failure')).toBeInTheDocument();
    });
  });

  it('renders empty state', async () => {
    mockUseContracts.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractListPage />);

    await waitFor(() => {
      expect(screen.getByText('No contracts yet')).toBeInTheDocument();
      expect(screen.getByText('Create your first contract')).toBeInTheDocument();
    });
  });

  it('renders contract cards with name, version, and status', async () => {
    mockUseContracts.mockReturnValue({
      data: {
        items: [
          {
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
        ],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractListPage />);

    await waitFor(() => {
      expect(screen.getByText('Orders API')).toBeInTheDocument();
      expect(screen.getByText('v1.0.0')).toBeInTheDocument();
      expect(screen.getByText('published')).toBeInTheDocument();
    });
  });

  it('renders "New Contract" button', async () => {
    mockUseContracts.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ContractListPage />);

    await waitFor(() => {
      expect(screen.getByText('New Contract')).toBeInTheDocument();
    });
  });

  describe('persona access tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    personas.forEach((persona) => {
      it(`${persona} can access ContractListPage`, async () => {
        mockAuth.mockReturnValue(createAuthMock(persona));
        mockUseContracts.mockReturnValue({
          data: { items: [] },
          isLoading: false,
          error: null,
        });

        renderWithProviders(<ContractListPage />);

        await waitFor(() => {
          expect(screen.getByText('Contracts')).toBeInTheDocument();
        });
      });
    });
  });
});
