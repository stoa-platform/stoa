/**
 * Tests for MarketplacePage (CAB-1453)
 *
 * Unified marketplace combining APIs and MCP Servers.
 * Page-level functional tests covering all personas.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { MarketplacePage } from '../marketplace/MarketplacePage';
import { renderWithProviders, createAuthMock, mockAPI, mockMCPServer } from '../../test/helpers';
import type { MarketplaceItem, MarketplaceStats, MarketplaceCategory } from '../../types';

// Mock hooks
const mockUseMarketplace = vi.fn();
const mockUseFeaturedItems = vi.fn();

vi.mock('../../hooks/useMarketplace', () => ({
  useMarketplace: (filters: Record<string, unknown>) => mockUseMarketplace(filters),
  useFeaturedItems: () => mockUseFeaturedItems(),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock i18n
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
    features: { enableI18n: false, enableMarketplace: true },
  },
}));

// ============ Test Data ============

function createMarketplaceItem(overrides: Partial<MarketplaceItem> = {}): MarketplaceItem {
  return {
    id: 'api-api-1',
    type: 'api',
    name: 'Payment API',
    displayName: 'Payment API',
    description: 'Process payments securely',
    category: 'Finance',
    tags: ['payments', 'fintech'],
    status: 'published',
    version: '2.1.0',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-02-01T00:00:00Z',
    api: mockAPI() as MarketplaceItem['api'],
    ...overrides,
  };
}

function createMCPMarketplaceItem(overrides: Partial<MarketplaceItem> = {}): MarketplaceItem {
  return {
    id: 'mcp-server-1',
    type: 'mcp-server',
    name: 'stoa-platform',
    displayName: 'STOA Platform Tools',
    description: 'Core STOA administration tools',
    category: 'platform',
    tags: ['list-apis', 'create-api'],
    status: 'active',
    version: '1.0.0',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-02-01T00:00:00Z',
    mcpServer: mockMCPServer() as MarketplaceItem['mcpServer'],
    ...overrides,
  };
}

const mockCategories: MarketplaceCategory[] = [
  { id: 'Finance', name: 'Finance', count: 1 },
  { id: 'platform', name: 'platform', count: 1 },
];

const mockStats: MarketplaceStats = {
  totalAPIs: 1,
  totalMCPServers: 1,
  totalItems: 2,
  categories: mockCategories,
};

const mockItems: MarketplaceItem[] = [createMarketplaceItem(), createMCPMarketplaceItem()];

describe('MarketplacePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockUseMarketplace.mockReturnValue({
      data: { items: mockItems, total: 2, stats: mockStats },
      isLoading: false,
      isError: false,
    });
    mockUseFeaturedItems.mockReturnValue({
      data: mockItems.map((item) => ({ ...item, featured: true })),
    });
  });

  describe('Page Structure', () => {
    it('should render page header with title', () => {
      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('Marketplace')).toBeInTheDocument();
      expect(
        screen.getByText('Discover APIs and AI tools available on the platform')
      ).toBeInTheDocument();
    });

    it('should render search input', () => {
      renderWithProviders(<MarketplacePage />);

      expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
    });

    it('should render type filter buttons', () => {
      renderWithProviders(<MarketplacePage />);

      expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'APIs' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'AI Tools' })).toBeInTheDocument();
    });

    it('should render stats bar', () => {
      renderWithProviders(<MarketplacePage />);

      // Stats bar shows totalAPIs=1, totalMCPServers=1, totalItems=2
      expect(screen.getByText('2')).toBeInTheDocument(); // totalItems (unique)
      expect(screen.getByText('Total')).toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('should show loading spinner when data is loading', () => {
      mockUseMarketplace.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      });

      const { container } = renderWithProviders(<MarketplacePage />);

      expect(container.querySelector('.animate-spin')).toBeTruthy();
    });
  });

  describe('Error State', () => {
    it('should show error message when fetch fails', () => {
      mockUseMarketplace.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      });

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('should show empty state when no items match filters', () => {
      mockUseMarketplace.mockReturnValue({
        data: { items: [], total: 0, stats: mockStats },
        isLoading: false,
        isError: false,
      });

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText(/no items match/i)).toBeInTheDocument();
    });
  });

  describe('Data State', () => {
    it('should render marketplace cards', () => {
      renderWithProviders(<MarketplacePage />);

      // Cards appear in both featured and main grid
      expect(screen.getAllByText('Payment API').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('STOA Platform Tools').length).toBeGreaterThanOrEqual(1);
    });

    it('should display results count', () => {
      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('2 items found')).toBeInTheDocument();
    });

    it('should display singular count when one item', () => {
      mockUseMarketplace.mockReturnValue({
        data: { items: [mockItems[0]], total: 1, stats: mockStats },
        isLoading: false,
        isError: false,
      });

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('1 item found')).toBeInTheDocument();
    });
  });

  describe('Featured Section', () => {
    it('should show featured section on first page without filters', () => {
      renderWithProviders(<MarketplacePage />);

      // "Featured" appears as h2 heading + card badges; use heading role
      expect(screen.getByRole('heading', { name: 'Featured' })).toBeInTheDocument();
    });

    it('should hide featured section when no featured items', () => {
      mockUseFeaturedItems.mockReturnValue({ data: [] });

      renderWithProviders(<MarketplacePage />);

      expect(screen.queryByText('Featured')).not.toBeInTheDocument();
    });
  });

  describe('Pagination', () => {
    it('should show pagination when total pages > 1', () => {
      mockUseMarketplace.mockReturnValue({
        data: { items: mockItems, total: 25, stats: mockStats },
        isLoading: false,
        isError: false,
      });

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('Previous')).toBeInTheDocument();
      expect(screen.getByText('Next')).toBeInTheDocument();
      expect(screen.getByText(/Page 1 of/)).toBeInTheDocument();
    });

    it('should not show pagination when total pages = 1', () => {
      renderWithProviders(<MarketplacePage />);

      expect(screen.queryByText('Previous')).not.toBeInTheDocument();
      expect(screen.queryByText('Next')).not.toBeInTheDocument();
    });
  });

  describe('Persona-based Tests', () => {
    it('should render for cpi-admin', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('Marketplace')).toBeInTheDocument();
      expect(screen.getAllByText('Payment API').length).toBeGreaterThanOrEqual(1);
    });

    it('should render for tenant-admin', () => {
      mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('Marketplace')).toBeInTheDocument();
      expect(screen.getAllByText('Payment API').length).toBeGreaterThanOrEqual(1);
    });

    it('should render for devops', () => {
      mockUseAuth.mockReturnValue(createAuthMock('devops'));

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('Marketplace')).toBeInTheDocument();
      expect(screen.getAllByText('Payment API').length).toBeGreaterThanOrEqual(1);
    });

    it('should render for viewer', () => {
      mockUseAuth.mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(<MarketplacePage />);

      expect(screen.getByText('Marketplace')).toBeInTheDocument();
      expect(screen.getAllByText('Payment API').length).toBeGreaterThanOrEqual(1);
    });
  });
});
