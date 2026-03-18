import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ServiceCatalog } from '../services/ServiceCatalog';
import { renderWithProviders, createAuthMock, mockAPI } from '../../test/helpers';
import type { PersonaRole } from '../../test/helpers';

// Mock hooks
vi.mock('../../hooks/useAPIs', () => ({
  useAPIs: vi.fn(),
  useAPICategories: vi.fn(),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../contexts/EnvironmentContext', () => ({
  usePortalEnvironment: vi.fn(() => ({ activeEnvironment: 'prod' })),
}));

import { useAPIs, useAPICategories } from '../../hooks/useAPIs';
import { useAuth } from '../../contexts/AuthContext';

const mockAPIs = [
  mockAPI({ id: 'api-1', name: 'Payment API', category: 'Finance', status: 'published' }),
  mockAPI({ id: 'api-2', name: 'Invoice API', category: 'Finance', status: 'published' }),
  mockAPI({
    id: 'api-3',
    name: 'User Directory',
    category: 'Identity',
    status: 'published',
    tags: ['iam', 'ldap'],
  }),
  mockAPI({ id: 'api-4', name: 'Legacy Auth', category: 'Identity', status: 'deprecated' }),
];

function setupMocks(role: PersonaRole = 'cpi-admin') {
  vi.mocked(useAuth).mockReturnValue(createAuthMock(role) as ReturnType<typeof useAuth>);
  vi.mocked(useAPIs).mockReturnValue({
    data: { items: mockAPIs, total: 4, page: 1, pageSize: 100, totalPages: 1 },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useAPIs>);
  vi.mocked(useAPICategories).mockReturnValue({
    data: ['Finance', 'Identity'],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useAPICategories>);
}

describe('ServiceCatalog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMocks();
  });

  it('renders the page title and description', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText('Service Catalog')).toBeInTheDocument();
    expect(screen.getByText('Browse available APIs organized by category')).toBeInTheDocument();
  });

  it('groups APIs by category', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText('Finance')).toBeInTheDocument();
    expect(screen.getByText('Identity')).toBeInTheDocument();
    // Both categories have 2 APIs each
    const counts = screen.getAllByText('(2)');
    expect(counts.length).toBe(2);
  });

  it('renders API cards with metadata', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('Invoice API')).toBeInTheDocument();
    expect(screen.getByText('User Directory')).toBeInTheDocument();
  });

  it('displays status badges', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    const publishedBadges = screen.getAllByText('published');
    expect(publishedBadges.length).toBe(3);
    expect(screen.getByText('deprecated')).toBeInTheDocument();
  });

  it('displays tags on API cards', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText('iam')).toBeInTheDocument();
    expect(screen.getByText('ldap')).toBeInTheDocument();
  });

  it('shows results count with categories', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText(/4 services across 2 categories/)).toBeInTheDocument();
  });

  it('renders search input', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(
      screen.getByPlaceholderText('Search APIs by name, description, or tag...')
    ).toBeInTheDocument();
  });

  it('renders status filter dropdown', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText('All statuses')).toBeInTheDocument();
  });

  it('allows collapsing category sections', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ServiceCatalog />, { route: '/services' });

    // Finance category header is a button
    const financeButton = screen.getByRole('button', { name: /Finance/ });
    await user.click(financeButton);

    // After collapse, cards should be hidden
    expect(screen.queryByText('Payment API')).not.toBeInTheDocument();
    // Identity category still visible
    expect(screen.getByText('User Directory')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    vi.mocked(useAPIs).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useAPIs>);

    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    // Loader2 spinner is rendered (svg element)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows error state with retry', () => {
    vi.mocked(useAPIs).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useAPIs>);

    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText('Failed to load services')).toBeInTheDocument();
    expect(screen.getByText('Try again')).toBeInTheDocument();
  });

  it('shows empty state when no APIs match', () => {
    vi.mocked(useAPIs).mockReturnValue({
      data: { items: [], total: 0, page: 1, pageSize: 100, totalPages: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useAPIs>);

    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    expect(screen.getByText('No services found')).toBeInTheDocument();
  });

  it('links API cards to detail page', () => {
    renderWithProviders(<ServiceCatalog />, { route: '/services' });
    const paymentLink = screen.getByText('Payment API').closest('a');
    expect(paymentLink).toHaveAttribute('href', '/apis/api-1');
  });

  // Persona-based tests
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      it(`renders for ${role}`, () => {
        setupMocks(role);
        renderWithProviders(<ServiceCatalog />, { route: '/services' });
        expect(screen.getByText('Service Catalog')).toBeInTheDocument();
        expect(screen.getByText('Payment API')).toBeInTheDocument();
      });
    }
  );
});
