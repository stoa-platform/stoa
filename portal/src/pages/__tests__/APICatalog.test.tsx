/**
 * Tests for APICatalog page (CAB-1133)
 *
 * Browse and discover available APIs in the marketplace.
 * Page-level functional tests covering all personas.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { APICatalog } from '../apis/APICatalog';
import { renderWithProviders, createAuthMock, mockAPI } from '../../test/helpers';
import type { API } from '../../types';

// Mock hooks
const mockUseAPIs = vi.fn();
const mockUseAPICategories = vi.fn();
const mockUseUniverses = vi.fn();
const mockUseQueryClient = vi.fn();

vi.mock('../../hooks/useAPIs', () => ({
  useAPIs: (params: Record<string, unknown>) => mockUseAPIs(params),
  useAPICategories: () => mockUseAPICategories(),
  useUniverses: () => mockUseUniverses(),
}));

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: () => mockUseQueryClient(),
  };
});

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock i18n — disable to use fallback strings
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../i18n', () => ({
  loadNamespace: vi.fn(),
  LANGUAGE_KEY: 'stoa:language',
}));

vi.mock('../../config', () => ({
  config: {
    api: { baseUrl: 'https://api.gostoa.dev', timeout: 30000 },
    mcp: { baseUrl: 'https://mcp.gostoa.dev', timeout: 30000 },
    features: { enableI18n: false },
  },
}));

// Mock components as stubs
vi.mock('../../components/apis/APICard', () => ({
  APICard: ({ api }: { api: API }) => <div data-testid={`api-card-${api.id}`}>{api.name}</div>,
}));

vi.mock('../../components/apis/APIFilters', () => ({
  APIFilters: ({
    search,
    category,
    universe,
    audience,
    audienceOptions,
  }: {
    search: string;
    category: string;
    universe: string;
    audience: string;
    audienceOptions: { id: string; label: string }[];
  }) => (
    <div data-testid="api-filters">
      <input data-testid="search-input" value={search} readOnly />
      <input data-testid="category-input" value={category} readOnly />
      <input data-testid="universe-input" value={universe} readOnly />
      <input data-testid="audience-input" value={audience} readOnly />
      <span data-testid="audience-options-count">{audienceOptions?.length ?? 0}</span>
      {audienceOptions?.map((opt: { id: string; label: string }) => (
        <span key={opt.id} data-testid={`audience-opt-${opt.id}`}>
          {opt.label}
        </span>
      ))}
    </div>
  ),
}));

describe('APICatalog', () => {
  const mockAPIs: API[] = [
    mockAPI({ id: 'api-1', name: 'Payment API' }),
    mockAPI({ id: 'api-2', name: 'Orders API' }),
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockUseAPIs.mockReturnValue({
      data: { items: mockAPIs, total: 2 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAPICategories.mockReturnValue({
      data: ['Finance', 'Logistics'],
      isLoading: false,
    });
    mockUseUniverses.mockReturnValue({
      data: ['production', 'staging'],
    });
    mockUseQueryClient.mockReturnValue({
      prefetchQuery: vi.fn(),
    });
  });

  describe('Page Structure', () => {
    it('should render page header with title', () => {
      renderWithProviders(<APICatalog />);

      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByText('Browse and discover available APIs')).toBeInTheDocument();
    });

    it('should render filters component', () => {
      renderWithProviders(<APICatalog />);

      expect(screen.getByTestId('api-filters')).toBeInTheDocument();
    });

    it('should render grid/list view toggle buttons', () => {
      renderWithProviders(<APICatalog />);

      const buttons = screen.getAllByRole('button');
      const gridButton = buttons.find((btn) => btn.getAttribute('title') === 'Grid view');
      const listButton = buttons.find((btn) => btn.getAttribute('title') === 'List view');

      expect(gridButton).toBeInTheDocument();
      expect(listButton).toBeInTheDocument();
    });

    it('should render refresh button', () => {
      renderWithProviders(<APICatalog />);

      const refreshButton = screen.getByTitle('Refresh');
      expect(refreshButton).toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('should show loading spinner when APIs are loading', () => {
      mockUseAPIs.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('Loading APIs...')).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('should show error message when API fetch fails', () => {
      mockUseAPIs.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new Error('Network error'),
        refetch: vi.fn(),
      });

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('Failed to load APIs')).toBeInTheDocument();
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });

    it('should show retry button on error', () => {
      const mockRefetch = vi.fn();
      mockUseAPIs.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new Error('Network error'),
        refetch: mockRefetch,
      });

      renderWithProviders(<APICatalog />);

      const retryButton = screen.getByText('Try Again');
      expect(retryButton).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('should show empty state when no APIs available', () => {
      mockUseAPIs.mockReturnValue({
        data: { items: [], total: 0 },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('No APIs Found')).toBeInTheDocument();
    });

    it('should show no filters message when no results without filters', () => {
      mockUseAPIs.mockReturnValue({
        data: { items: [], total: 0 },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<APICatalog />);

      // Without filters, should show generic empty message
      expect(screen.getByText('No APIs Found')).toBeInTheDocument();
      expect(screen.getByText(/There are no published APIs available yet/)).toBeInTheDocument();
    });
  });

  describe('Data State', () => {
    it('should render API cards in grid view by default', () => {
      renderWithProviders(<APICatalog />);

      expect(screen.getByTestId('api-card-api-1')).toBeInTheDocument();
      expect(screen.getByTestId('api-card-api-2')).toBeInTheDocument();
    });

    it('should display results count', () => {
      renderWithProviders(<APICatalog />);

      expect(screen.getByText('2 APIs available')).toBeInTheDocument();
    });

    it('should display singular count when one API', () => {
      mockUseAPIs.mockReturnValue({
        data: { items: [mockAPIs[0]], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('1 API available')).toBeInTheDocument();
    });
  });

  describe('Pagination', () => {
    it('should show pagination when total pages > 1', () => {
      mockUseAPIs.mockReturnValue({
        data: { items: mockAPIs, total: 25 }, // 25 items with pageSize 12 = 3 pages
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
      expect(screen.getByText('Previous')).toBeInTheDocument();
      expect(screen.getByText('Next')).toBeInTheDocument();
    });

    it('should not show pagination when total pages = 1', () => {
      renderWithProviders(<APICatalog />);

      expect(screen.queryByText('Previous')).not.toBeInTheDocument();
      expect(screen.queryByText('Next')).not.toBeInTheDocument();
    });
  });

  describe('Persona-based Tests', () => {
    it('should render for cpi-admin', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByTestId('api-card-api-1')).toBeInTheDocument();
    });

    it('should render for tenant-admin', () => {
      mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByTestId('api-card-api-1')).toBeInTheDocument();
    });

    it('should render for devops', () => {
      mockUseAuth.mockReturnValue(createAuthMock('devops'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByTestId('api-card-api-1')).toBeInTheDocument();
    });

    it('should render for viewer', () => {
      mockUseAuth.mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByTestId('api-card-api-1')).toBeInTheDocument();
    });
  });

  describe('Audience Visibility by Role (CAB-1323)', () => {
    it('cpi-admin should see all 3 audience options', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByTestId('audience-options-count').textContent).toBe('3');
      expect(screen.getByTestId('audience-opt-public')).toBeInTheDocument();
      expect(screen.getByTestId('audience-opt-internal')).toBeInTheDocument();
      expect(screen.getByTestId('audience-opt-partner')).toBeInTheDocument();
    });

    it('tenant-admin should see all 3 audience options', () => {
      mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByTestId('audience-options-count').textContent).toBe('3');
    });

    it('devops should see public + internal (2 options)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('devops'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByTestId('audience-options-count').textContent).toBe('2');
      expect(screen.getByTestId('audience-opt-public')).toBeInTheDocument();
      expect(screen.getByTestId('audience-opt-internal')).toBeInTheDocument();
      expect(screen.queryByTestId('audience-opt-partner')).not.toBeInTheDocument();
    });

    it('viewer should see only public (1 option)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(<APICatalog />);

      expect(screen.getByTestId('audience-options-count').textContent).toBe('1');
      expect(screen.getByTestId('audience-opt-public')).toBeInTheDocument();
      expect(screen.queryByTestId('audience-opt-internal')).not.toBeInTheDocument();
      expect(screen.queryByTestId('audience-opt-partner')).not.toBeInTheDocument();
    });

    it('should pass audience param to useAPIs', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(<APICatalog />);

      // useAPIs is called with audience: undefined (no filter selected initially)
      expect(mockUseAPIs).toHaveBeenCalledWith(expect.objectContaining({ audience: undefined }));
    });
  });
});
