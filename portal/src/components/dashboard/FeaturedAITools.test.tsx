/**
 * Tests for FeaturedAITools (CAB-1390)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { FeaturedAITools } from './FeaturedAITools';
import { renderWithProviders } from '../../test/helpers';
import type { AIToolPreview } from '../../hooks/useDashboard';

vi.mock('../../config', () => ({
  config: {
    features: { enableMCPTools: true },
  },
}));

const mockUseFeaturedAITools = vi.fn();

vi.mock('../../hooks/useDashboard', () => ({
  useFeaturedAITools: (...args: unknown[]) => mockUseFeaturedAITools(...args),
  useFeaturedAPIs: vi.fn(() => ({ data: [], isLoading: false })),
  useDashboardStats: vi.fn(() => ({ data: null, isLoading: false })),
  useRecentActivity: vi.fn(() => ({ data: [], isLoading: false })),
}));

const mockTool = (overrides: Partial<AIToolPreview> = {}): AIToolPreview => ({
  id: 'tool-1',
  name: 'stoa-platform',
  displayName: 'STOA Platform Tools',
  description: 'Core STOA administration tools',
  category: 'platform',
  status: 'active',
  tools: [{ id: 't-1', displayName: 'List APIs' }],
  ...overrides,
});

describe('FeaturedAITools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseFeaturedAITools.mockReturnValue({ data: undefined, isLoading: false });
  });

  it('shows loading skeletons when isLoading is true', () => {
    mockUseFeaturedAITools.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderWithProviders(<FeaturedAITools />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows empty state when no tools are available', () => {
    mockUseFeaturedAITools.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText('No AI tools available')).toBeInTheDocument();
  });

  it('renders tool cards when data is available', () => {
    mockUseFeaturedAITools.mockReturnValue({
      data: [mockTool(), mockTool({ id: 'tool-2', displayName: 'Tenant Tools' })],
      isLoading: false,
    });
    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText('STOA Platform Tools')).toBeInTheDocument();
    expect(screen.getByText('Tenant Tools')).toBeInTheDocument();
  });

  it('shows tool description', () => {
    mockUseFeaturedAITools.mockReturnValue({
      data: [mockTool()],
      isLoading: false,
    });
    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText('Core STOA administration tools')).toBeInTheDocument();
  });

  it('renders "Browse all tools" link', () => {
    mockUseFeaturedAITools.mockReturnValue({ data: [mockTool()], isLoading: false });
    renderWithProviders(<FeaturedAITools />);
    expect(screen.getByText(/browse all tools/i)).toBeInTheDocument();
  });
});
