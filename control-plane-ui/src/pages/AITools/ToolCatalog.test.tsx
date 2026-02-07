import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock mcpGatewayService
const mockGetTools = vi.fn().mockResolvedValue({
  tools: [
    { name: 'weather-api', displayName: 'Weather API', description: 'Get weather forecasts', tags: ['weather', 'forecast'], isActive: true },
    { name: 'translate-api', displayName: 'Translate API', description: 'Text translation service', tags: ['nlp', 'translate'], isActive: true },
  ],
  totalCount: 2,
});
const mockGetToolTags = vi.fn().mockResolvedValue(['weather', 'nlp', 'forecast', 'translate']);

vi.mock('../../services/mcpGatewayApi', () => ({
  mcpGatewayService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    getTools: (...args: unknown[]) => mockGetTools(...args),
    getToolTags: (...args: unknown[]) => mockGetToolTags(...args),
  },
}));

// Mock ToolCard component
vi.mock('../../components/tools', () => ({
  ToolCard: ({ tool, onClick }: { tool: { name: string; displayName: string; description: string }; onClick: () => void }) => (
    <div data-testid={`tool-card-${tool.name}`} onClick={onClick}>
      <h3>{tool.displayName}</h3>
      <p>{tool.description}</p>
    </div>
  ),
}));

// Mock shared components
vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: () => <div data-testid="empty-state">No tools found</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { ToolCatalog } from './ToolCatalog';

function renderComponent() {
  return render(
    <MemoryRouter>
      <ToolCatalog />
    </MemoryRouter>
  );
}

describe('ToolCatalog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'AI Tool Catalog' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(await screen.findByText(/Browse MCP tools available/)).toBeInTheDocument();
  });

  it('shows tool cards after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    expect(screen.getByText('Translate API')).toBeInTheDocument();
  });

  it('shows tool descriptions', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Get weather forecasts')).toBeInTheDocument();
    });
    expect(screen.getByText('Text translation service')).toBeInTheDocument();
  });

  it('shows results count', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Showing 2 of 2 tools')).toBeInTheDocument();
    });
  });

  it('shows search input', async () => {
    renderComponent();
    expect(await screen.findByPlaceholderText('Search tools by name or description...')).toBeInTheDocument();
  });

  it('shows tag filter dropdown', async () => {
    renderComponent();
    expect(await screen.findByText('All Tags')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    renderComponent();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('calls getTools with correct parameters', async () => {
    renderComponent();
    await waitFor(() => {
      expect(mockGetTools).toHaveBeenCalledWith({
        search: undefined,
        tag: undefined,
        tenant: undefined,
        limit: 50,
      });
    });
  });
});
