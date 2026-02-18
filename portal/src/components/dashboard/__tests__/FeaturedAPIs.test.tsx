import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../../test/helpers';

const mockUseFeaturedAPIs = vi.fn();
vi.mock('../../../hooks/useDashboard', () => ({
  useFeaturedAPIs: () => mockUseFeaturedAPIs(),
}));

vi.mock('../../../config', () => ({
  config: {
    features: {
      enableAPICatalog: true,
    },
  },
}));

import { FeaturedAPIs } from '../FeaturedAPIs';

const mockAPIs = [
  {
    id: 'api-1',
    name: 'payment-api',
    displayName: 'Payment API',
    description: 'Process payments securely',
    version: '2.1.0',
    status: 'published',
    category: 'Finance',
    tags: ['payments', 'fintech'],
    visibility: 'public' as const,
  },
  {
    id: 'api-2',
    name: 'orders-api',
    displayName: 'Orders API',
    description: 'Order management service',
    version: '1.0.0',
    status: 'published',
    category: 'Commerce',
    tags: ['orders'],
    visibility: 'internal' as const,
  },
];

describe('FeaturedAPIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseFeaturedAPIs.mockReturnValue({
      data: [],
      isLoading: false,
    });
  });

  it('renders the API Catalog heading', () => {
    renderWithProviders(<FeaturedAPIs />);

    expect(screen.getByText('API Catalog')).toBeInTheDocument();
  });

  it('renders browse all APIs link', () => {
    renderWithProviders(<FeaturedAPIs />);

    expect(screen.getByText('Browse all APIs')).toBeInTheDocument();
  });

  it('renders empty state when no APIs', () => {
    renderWithProviders(<FeaturedAPIs />);

    expect(screen.getByText('No APIs available')).toBeInTheDocument();
  });

  it('renders loading skeleton when loading', () => {
    mockUseFeaturedAPIs.mockReturnValue({
      data: [],
      isLoading: true,
    });

    const { container } = renderWithProviders(<FeaturedAPIs />);

    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders API cards when APIs are available', () => {
    mockUseFeaturedAPIs.mockReturnValue({
      data: mockAPIs,
      isLoading: false,
    });

    renderWithProviders(<FeaturedAPIs />);

    expect(screen.getByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('Orders API')).toBeInTheDocument();
  });

  it('renders API descriptions', () => {
    mockUseFeaturedAPIs.mockReturnValue({
      data: mockAPIs,
      isLoading: false,
    });

    renderWithProviders(<FeaturedAPIs />);

    expect(screen.getByText('Process payments securely')).toBeInTheDocument();
  });

  it('renders tags for APIs with tags', () => {
    mockUseFeaturedAPIs.mockReturnValue({
      data: mockAPIs,
      isLoading: false,
    });

    renderWithProviders(<FeaturedAPIs />);

    expect(screen.getByText('payments, fintech')).toBeInTheDocument();
  });

  it('browse link points to /apis route', () => {
    renderWithProviders(<FeaturedAPIs />);

    const link = screen.getByText('Browse all APIs').closest('a');
    expect(link).toHaveAttribute('href', '/apis');
  });
});
