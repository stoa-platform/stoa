import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { EUApiCatalog } from './EUApiCatalog';
import type { CatalogResponse } from '../../types';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetCatalog = vi.fn();
vi.mock('../../services/discoveryApi', () => ({
  discoveryService: { getCatalog: (...args: unknown[]) => mockGetCatalog(...args) },
}));

const mockCreateBackendApi = vi.fn();
vi.mock('../../services/backendApisApi', () => ({
  backendApisService: { createBackendApi: (...args: unknown[]) => mockCreateBackendApi(...args) },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="skeleton" />,
}));

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const mockCatalog: CatalogResponse = {
  total: 2,
  categories: [
    { id: 'finance', name: 'Finance & Banking' },
    { id: 'statistics', name: 'Statistics' },
  ],
  entries: [
    {
      id: 'eu-ecb-sdw',
      name: 'ecb-sdw',
      display_name: 'ECB Statistical Data Warehouse',
      description: 'ECB exchange rates and monetary statistics',
      category: 'finance',
      country: 'EU',
      region: 'EU',
      spec_url: 'https://data-api.ecb.europa.eu/service',
      protocol: 'openapi',
      auth_type: 'none',
      tools: [],
      status: 'verified',
      tags: ['finance', 'ecb'],
      documentation_url: 'https://data.ecb.europa.eu/',
    },
    {
      id: 'fr-data-gouv',
      name: 'data-gouv',
      display_name: 'data.gouv.fr',
      description: 'French open data portal',
      category: 'statistics',
      country: 'FR',
      region: 'EU',
      spec_url: 'https://www.data.gouv.fr/api/1',
      protocol: 'openapi',
      auth_type: 'api_key',
      tools: [],
      status: 'community',
      tags: ['statistics', 'france'],
    },
  ],
};

// cpi-admin persona has tenant_id: 'gregarious-games'
const TENANT_ID = 'gregarious-games';

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('EUApiCatalog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin') as ReturnType<typeof useAuth>);
    mockGetCatalog.mockResolvedValue(mockCatalog);
    mockCreateBackendApi.mockResolvedValue({ id: 'bapi-new' });
  });

  it('renders catalog entries after load', async () => {
    renderWithProviders(<EUApiCatalog />);

    await waitFor(() => {
      expect(screen.getByText('ECB Statistical Data Warehouse')).toBeInTheDocument();
      expect(screen.getByText('data.gouv.fr')).toBeInTheDocument();
    });
  });

  it('shows skeleton while loading', () => {
    mockGetCatalog.mockReturnValue(new Promise(() => {})); // never resolves
    renderWithProviders(<EUApiCatalog />);
    expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0);
  });

  it('displays total count in header', async () => {
    renderWithProviders(<EUApiCatalog />);
    await waitFor(() => screen.getByText('ECB Statistical Data Warehouse'));
    expect(screen.getByText(/2 curated EU public APIs/)).toBeInTheDocument();
  });

  it('filters entries by category', async () => {
    renderWithProviders(<EUApiCatalog />);

    await waitFor(() => screen.getByText('ECB Statistical Data Warehouse'));

    fireEvent.click(screen.getByText('Finance & Banking'));

    await waitFor(() => {
      expect(screen.getByText('ECB Statistical Data Warehouse')).toBeInTheDocument();
      expect(screen.queryByText('data.gouv.fr')).not.toBeInTheDocument();
    });
  });

  it('filters entries by country', async () => {
    renderWithProviders(<EUApiCatalog />);

    await waitFor(() => screen.getByText('ECB Statistical Data Warehouse'));

    const countrySelect = screen.getByRole('combobox', { name: /filter by country/i });
    fireEvent.change(countrySelect, { target: { value: 'FR' } });

    await waitFor(() => {
      expect(screen.queryByText('ECB Statistical Data Warehouse')).not.toBeInTheDocument();
      expect(screen.getByText('data.gouv.fr')).toBeInTheDocument();
    });
  });

  it('opens deploy dialog on Deploy click', async () => {
    renderWithProviders(<EUApiCatalog />);

    await waitFor(() => screen.getByText('ECB Statistical Data Warehouse'));

    const deployButtons = screen.getAllByText('Deploy');
    fireEvent.click(deployButtons[0]);

    expect(screen.getByText(/Deploy ECB Statistical Data Warehouse/)).toBeInTheDocument();
    expect(screen.getByText('Confirm Deploy')).toBeInTheDocument();
  });

  it('calls createBackendApi on confirm deploy', async () => {
    renderWithProviders(<EUApiCatalog />);

    await waitFor(() => screen.getByText('ECB Statistical Data Warehouse'));

    fireEvent.click(screen.getAllByText('Deploy')[0]);
    fireEvent.click(screen.getByText('Confirm Deploy'));

    await waitFor(() => {
      expect(mockCreateBackendApi).toHaveBeenCalledWith(
        TENANT_ID,
        expect.objectContaining({
          name: 'ecb-sdw',
          display_name: 'ECB Statistical Data Warehouse',
          auth_type: 'none',
        })
      );
    });
  });

  it('closes deploy dialog on Cancel', async () => {
    renderWithProviders(<EUApiCatalog />);

    await waitFor(() => screen.getByText('ECB Statistical Data Warehouse'));

    fireEvent.click(screen.getAllByText('Deploy')[0]);
    expect(screen.getByText('Confirm Deploy')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Cancel'));
    await waitFor(() => {
      expect(screen.queryByText('Confirm Deploy')).not.toBeInTheDocument();
    });
  });

  it('shows empty state when filters match nothing', async () => {
    renderWithProviders(<EUApiCatalog />);

    await waitFor(() => screen.getByText('ECB Statistical Data Warehouse'));

    // Filter Finance then switch to FR-only country — no overlap
    fireEvent.click(screen.getByText('Finance & Banking'));
    const countrySelect = screen.getByRole('combobox', { name: /filter by country/i });
    fireEvent.change(countrySelect, { target: { value: 'FR' } });

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });
});
