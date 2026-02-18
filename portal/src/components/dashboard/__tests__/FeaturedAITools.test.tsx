import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../../test/helpers';

// Mock hook with wrapper pattern for stable reference
const mockUseFeaturedAITools = vi.fn();
vi.mock('../../../hooks/useDashboard', () => ({
  useFeaturedAITools: () => mockUseFeaturedAITools(),
}));

vi.mock('../../../config', () => ({
  config: {
    features: {
      enableMCPTools: true,
    },
  },
}));

import { FeaturedAITools } from '../FeaturedAITools';

const mockTools = [
  {
    id: 'tool-server-1',
    name: 'stoa-platform',
    displayName: 'STOA Platform Tools',
    description: 'Core STOA administration tools',
    category: 'platform' as const,
    status: 'active',
    tools: [
      { id: 't1', displayName: 'List APIs' },
      { id: 't2', displayName: 'Create API' },
    ],
  },
  {
    id: 'tool-server-2',
    name: 'analytics-server',
    displayName: 'Analytics Server',
    description: 'Usage analytics tools',
    category: 'tenant' as const,
    status: 'active',
    tools: [{ id: 't3', displayName: 'Get Usage' }],
  },
];

describe('FeaturedAITools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseFeaturedAITools.mockReturnValue({
      data: [],
      isLoading: false,
    });
  });

  it('renders the AI Tools heading', () => {
    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText('AI Tools')).toBeInTheDocument();
  });

  it('renders browse all link', () => {
    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText('Browse all tools')).toBeInTheDocument();
  });

  it('renders empty state when no tools', () => {
    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText('No AI tools available')).toBeInTheDocument();
  });

  it('renders loading skeleton when loading', () => {
    mockUseFeaturedAITools.mockReturnValue({
      data: [],
      isLoading: true,
    });

    const { container } = renderWithProviders(<FeaturedAITools />);
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders tool cards when tools are available', () => {
    mockUseFeaturedAITools.mockReturnValue({
      data: mockTools,
      isLoading: false,
    });

    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText('STOA Platform Tools')).toBeInTheDocument();
    expect(screen.getByText('Analytics Server')).toBeInTheDocument();
  });

  it('renders tool count for each server', () => {
    mockUseFeaturedAITools.mockReturnValue({
      data: mockTools,
      isLoading: false,
    });

    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText(/2 tools/)).toBeInTheDocument();
    expect(screen.getByText(/1 tools/)).toBeInTheDocument();
  });
});
