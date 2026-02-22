/**
 * Tests for FeaturedAPIs (CAB-1390)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { FeaturedAPIs } from './FeaturedAPIs';
import { renderWithProviders, mockAPI } from '../../test/helpers';

vi.mock('../../config', () => ({
  config: {
    features: { enableAPICatalog: true },
  },
}));

const mockUseFeaturedAPIs = vi.fn();

vi.mock('../../hooks/useDashboard', () => ({
  useFeaturedAPIs: (...args: unknown[]) => mockUseFeaturedAPIs(...args),
  useFeaturedAITools: vi.fn(() => ({ data: [], isLoading: false })),
  useDashboardStats: vi.fn(() => ({ data: null, isLoading: false })),
  useRecentActivity: vi.fn(() => ({ data: [], isLoading: false })),
}));

describe('FeaturedAPIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseFeaturedAPIs.mockReturnValue({ data: undefined, isLoading: false });
  });

  it('shows loading skeletons when isLoading is true', () => {
    mockUseFeaturedAPIs.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderWithProviders(<FeaturedAPIs />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows empty state when no APIs are returned', () => {
    mockUseFeaturedAPIs.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<FeaturedAPIs />);
    // Empty state: some informational text appears
    expect(screen.getByText('No APIs available')).toBeInTheDocument();
  });

  it('renders API cards when data is available', () => {
    mockUseFeaturedAPIs.mockReturnValue({
      data: [mockAPI(), mockAPI({ id: 'api-2', name: 'Orders API' })],
      isLoading: false,
    });
    renderWithProviders(<FeaturedAPIs />);
    expect(screen.getByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('Orders API')).toBeInTheDocument();
  });

  it('shows no individual API card links when data is empty', () => {
    // vi.doMock cannot re-import already-bound modules in vitest; test behavioral outcome.
    // With enableAPICatalog: true (top-level mock) + empty data:
    //   - Header "Browse all APIs" link is rendered
    //   - No individual API card links (only header link)
    mockUseFeaturedAPIs.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<FeaturedAPIs />);
    const links = screen.getAllByRole('link');
    // Only 1 link: the "Browse all APIs" header link
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent(/browse all apis/i);
  });
});
