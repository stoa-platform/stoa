/**
 * FavoritesPage Tests - CAB-1470
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { FavoritesPage } from '../favorites/FavoritesPage';

const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

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
    features: { enableI18n: false },
  },
}));

const mockFavoritesData = vi.fn();
const mockRemoveFavorite = vi.fn();
const mockRemoveIsPending = vi.fn();

vi.mock('../../hooks/useFavorites', () => ({
  useFavorites: () => ({
    data: mockFavoritesData(),
    isLoading: false,
  }),
  useRemoveFavorite: () => ({
    mutate: mockRemoveFavorite,
    isPending: mockRemoveIsPending(),
  }),
}));

const sampleFavorites = [
  {
    id: 'f1',
    item_id: 'api-1',
    item_type: 'api' as const,
    item_name: 'Payment API',
    item_description: 'Process payments and manage transactions.',
    added_at: '2026-02-20T10:00:00Z',
  },
  {
    id: 'f2',
    item_id: 'mcp-1',
    item_type: 'mcp_server' as const,
    item_name: 'Analytics Server',
    item_description: 'Real-time analytics and reporting.',
    added_at: '2026-02-21T14:00:00Z',
  },
];

describe('FavoritesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
    mockFavoritesData.mockReturnValue({ favorites: sampleFavorites });
    mockRemoveIsPending.mockReturnValue(false);
  });

  it('renders the page heading and subtitle', async () => {
    renderWithProviders(<FavoritesPage />);
    await waitFor(() => {
      expect(screen.getByText('Favorites')).toBeInTheDocument();
    });
    expect(screen.getByText('Your bookmarked APIs and MCP servers')).toBeInTheDocument();
  });

  it('renders favorite items', async () => {
    renderWithProviders(<FavoritesPage />);
    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });
    expect(screen.getByText('Analytics Server')).toBeInTheDocument();
    expect(screen.getByText('API')).toBeInTheDocument();
    expect(screen.getByText('MCP Server')).toBeInTheDocument();
  });

  it('renders item descriptions', async () => {
    renderWithProviders(<FavoritesPage />);
    await waitFor(() => {
      expect(screen.getByText('Process payments and manage transactions.')).toBeInTheDocument();
    });
    expect(screen.getByText('Real-time analytics and reporting.')).toBeInTheDocument();
  });

  it('shows empty state when no favorites', async () => {
    mockFavoritesData.mockReturnValue({ favorites: [] });
    renderWithProviders(<FavoritesPage />);
    await waitFor(() => {
      expect(screen.getByText('No favorites yet')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Bookmark APIs and MCP servers from their detail pages')
    ).toBeInTheDocument();
  });

  it('calls removeFavorite when trash button clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<FavoritesPage />);
    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });
    const removeButtons = screen.getAllByRole('button', { name: /Remove .* from favorites/ });
    await user.click(removeButtons[0]);
    expect(mockRemoveFavorite).toHaveBeenCalledWith('f1');
  });

  it('renders View links for favorites', async () => {
    renderWithProviders(<FavoritesPage />);
    await waitFor(() => {
      expect(screen.getAllByText('View')).toHaveLength(2);
    });
  });

  it('returns null when not authenticated', () => {
    mockAuth.mockReturnValue({
      ...createAuthMock('cpi-admin'),
      isAuthenticated: false,
      isLoading: false,
    });
    const { container } = renderWithProviders(<FavoritesPage />);
    expect(container.innerHTML).toBe('');
  });

  describe('Persona-based Tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(personas)('%s can access favorites page', async (persona) => {
      mockAuth.mockReturnValue(createAuthMock(persona));
      renderWithProviders(<FavoritesPage />);
      await waitFor(() => {
        expect(screen.getByText('Favorites')).toBeInTheDocument();
      });
    });
  });
});
