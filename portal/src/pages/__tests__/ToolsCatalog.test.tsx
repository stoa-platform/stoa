/**
 * ToolsCatalog Tests - CAB-1167
 *
 * Tests for the tools catalog page with search, filters, and pagination.
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { ToolsCatalog } from '../tools/ToolsCatalog';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock hooks
const mockToolsData = vi.fn();
const mockCategoriesData = vi.fn();
const mockCategoriesWithCountsData = vi.fn();
const mockRefetch = vi.fn();

vi.mock('../../hooks/useTools', () => ({
  useTools: () => ({
    data: mockToolsData(),
    isLoading: false,
    isError: false,
    error: null,
    refetch: mockRefetch,
  }),
  useToolCategories: () => ({
    data: mockCategoriesData(),
  }),
  useToolCategoriesWithCounts: () => ({
    data: mockCategoriesWithCountsData(),
  }),
}));

describe('ToolsCatalog', () => {
  const mockTools = [
    {
      id: 'tool-1',
      name: 'tool-1',
      displayName: 'Test Tool 1',
      description: 'First test tool',
      status: 'active',
      category: 'Testing',
      tags: ['test', 'demo'],
      pricing: { model: 'free' },
      rateLimit: { requests: 100, period: 'hour' },
    },
    {
      id: 'tool-2',
      name: 'tool-2',
      displayName: 'Test Tool 2',
      description: 'Second test tool',
      status: 'beta',
      category: 'Development',
      tags: ['dev'],
      pricing: { model: 'paid' },
      rateLimit: { requests: 50, period: 'minute' },
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockToolsData.mockReturnValue({ tools: mockTools, total_count: 2 });
    mockCategoriesData.mockReturnValue(['Testing', 'Development']);
    mockCategoriesWithCountsData.mockReturnValue({
      categories: [
        { name: 'Testing', count: 1 },
        { name: 'Development', count: 1 },
      ],
    });
  });

  it('renders the page heading', () => {
    renderWithProviders(<ToolsCatalog />);
    expect(screen.getByText('AI Tools Catalog')).toBeInTheDocument();
  });

  it('renders search input', () => {
    renderWithProviders(<ToolsCatalog />);
    expect(screen.getByPlaceholderText('Search tools...')).toBeInTheDocument();
  });

  it('renders category filter', () => {
    renderWithProviders(<ToolsCatalog />);
    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBeGreaterThan(0);
  });

  it('renders refresh button', () => {
    renderWithProviders(<ToolsCatalog />);
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('displays tools in a grid', async () => {
    renderWithProviders(<ToolsCatalog />);
    await waitFor(() => {
      expect(screen.getByText('Test Tool 1')).toBeInTheDocument();
      expect(screen.getByText('Test Tool 2')).toBeInTheDocument();
    });
  });

  it('shows tool count', async () => {
    renderWithProviders(<ToolsCatalog />);
    await waitFor(() => {
      expect(screen.getByText('2 tools')).toBeInTheDocument();
    });
  });

  it('shows empty state when no tools', () => {
    mockToolsData.mockReturnValue({ tools: [], total_count: 0 });
    renderWithProviders(<ToolsCatalog />);
    expect(screen.getByText('No Tools Found')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.clearAllMocks();
        mockAuth.mockReturnValue(createAuthMock(role));
        mockToolsData.mockReturnValue({ tools: mockTools, total_count: 2 });
        mockCategoriesData.mockReturnValue(['Testing', 'Development']);
        mockCategoriesWithCountsData.mockReturnValue({
          categories: [
            { name: 'Testing', count: 1 },
            { name: 'Development', count: 1 },
          ],
        });
      });

      it('renders the page without error', async () => {
        renderWithProviders(<ToolsCatalog />);
        await waitFor(() => {
          expect(screen.getByText('AI Tools Catalog')).toBeInTheDocument();
        });
      });

      it('displays tools', async () => {
        renderWithProviders(<ToolsCatalog />);
        await waitFor(() => {
          expect(screen.getByText('Test Tool 1')).toBeInTheDocument();
          expect(screen.getByText('Test Tool 2')).toBeInTheDocument();
        });
      });
    }
  );
});
