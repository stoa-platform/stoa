import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { PersonaRole } from '../../test/helpers';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';

const mockListConnectors = vi.fn();
const mockAuthorize = vi.fn();
const mockDisconnect = vi.fn();
const mockPromote = vi.fn();

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
vi.mock('../../services/mcpConnectorsApi', () => ({
  mcpConnectorsService: {
    listConnectors: (...args: unknown[]) => mockListConnectors(...args),
    authorize: (...args: unknown[]) => mockAuthorize(...args),
    disconnect: (...args: unknown[]) => mockDisconnect(...args),
    promote: (...args: unknown[]) => mockPromote(...args),
  },
}));

const mockToast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => mockToast,
}));

const mockConfirm = vi.fn().mockResolvedValue(false);
vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [mockConfirm, () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { ConnectorCatalog } from './ConnectorCatalog';

const mockConnectors = [
  {
    id: '1',
    slug: 'linear',
    display_name: 'Linear',
    description: 'Project management for modern teams',
    icon_url: 'https://example.com/linear.png',
    category: 'project-management',
    mcp_base_url: 'https://mcp.linear.app',
    transport: 'sse',
    oauth_scopes: 'read write',
    oauth_pkce_required: true,
    documentation_url: 'https://linear.app/docs',
    is_featured: true,
    enabled: true,
    sort_order: 1,
    is_connected: true,
    connected_server_id: 'srv-1',
    connection_health: 'healthy',
    connected_environment: 'dev',
  },
  {
    id: '2',
    slug: 'github',
    display_name: 'GitHub',
    description: 'Code hosting and collaboration',
    icon_url: null,
    category: 'development',
    mcp_base_url: 'https://mcp.github.com',
    transport: 'streamable_http',
    oauth_scopes: 'repo',
    oauth_pkce_required: false,
    documentation_url: null,
    is_featured: true,
    enabled: true,
    sort_order: 2,
    is_connected: false,
    connected_server_id: null,
    connection_health: null,
  },
  {
    id: '3',
    slug: 'slack',
    display_name: 'Slack',
    description: 'Team communication',
    icon_url: null,
    category: 'communication',
    mcp_base_url: 'https://mcp.slack.com',
    transport: 'sse',
    oauth_scopes: null,
    oauth_pkce_required: false,
    documentation_url: null,
    is_featured: false,
    enabled: true,
    sort_order: 3,
    is_connected: false,
    connected_server_id: null,
    connection_health: null,
  },
  {
    id: '4',
    slug: 'datadog',
    display_name: 'Datadog',
    description: 'Monitoring and analytics',
    icon_url: null,
    category: 'monitoring',
    mcp_base_url: 'https://mcp.datadog.com',
    transport: 'sse',
    oauth_scopes: null,
    oauth_pkce_required: false,
    documentation_url: null,
    is_featured: false,
    enabled: true,
    sort_order: 4,
    is_connected: false,
    connected_server_id: null,
    connection_health: null,
  },
  {
    id: '5',
    slug: 'sentry',
    display_name: 'Sentry',
    description: 'Error tracking',
    icon_url: null,
    category: 'monitoring',
    mcp_base_url: 'https://mcp.sentry.io',
    transport: 'sse',
    oauth_scopes: null,
    oauth_pkce_required: false,
    documentation_url: null,
    is_featured: false,
    enabled: true,
    sort_order: 5,
    is_connected: false,
    connected_server_id: null,
    connection_health: null,
  },
];

function renderComponent() {
  return render(
    <MemoryRouter>
      <ConnectorCatalog />
    </MemoryRouter>
  );
}

describe('ConnectorCatalog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockListConnectors.mockResolvedValue({
      connectors: mockConnectors,
      total_count: mockConnectors.length,
    });
  });

  it('renders loading skeletons initially', () => {
    mockListConnectors.mockReturnValue(new Promise(() => {}));
    renderComponent();
    expect(screen.getAllByTestId('card-skeleton')).toHaveLength(6);
  });

  it('displays connector cards after loading', async () => {
    renderComponent();
    // Featured connectors appear in both Featured and All sections
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('GitHub').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Slack')).toBeInTheDocument();
    expect(screen.getByText('Datadog')).toBeInTheDocument();
    expect(screen.getByText('Sentry')).toBeInTheDocument();
  });

  it('shows category badges on cards', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('Project Management').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Development').length).toBeGreaterThan(0);
  });

  it('shows Connected badge for connected connectors', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Connected').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows Connect button for disconnected connectors', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });
    // GitHub appears in Featured + All = 2 Connect buttons for GitHub
    // Slack, Datadog, Sentry = 3 Connect buttons (non-featured)
    // Total: 2 (GitHub) + 3 (non-featured) = 5
    const connectButtons = screen.getAllByText('Connect');
    expect(connectButtons.length).toBe(5);
  });

  it('shows Disconnect button for connected connectors', async () => {
    renderComponent();
    await waitFor(() => {
      // Linear is connected and appears in Featured + All = 2 Disconnect buttons
      expect(screen.getAllByText('Disconnect').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders featured section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Featured')).toBeInTheDocument();
    });
  });

  it('filters by category', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });
    // "Monitoring" text appears as both category badge and filter button
    fireEvent.click(screen.getByRole('button', { name: 'Monitoring' }));
    // Category filter hides Featured section, so Linear is gone completely
    expect(screen.getByText('Datadog')).toBeInTheDocument();
    expect(screen.getByText('Sentry')).toBeInTheDocument();
    expect(screen.queryByText('Linear')).not.toBeInTheDocument();
  });

  it('calls authorize API on connect click', async () => {
    mockAuthorize.mockResolvedValue({ authorize_url: 'https://auth.example.com', state: 'xyz' });

    // Mock window.location.href assignment
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, href: 'http://localhost/' },
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('GitHub').length).toBeGreaterThanOrEqual(1);
    });

    // Click first Connect button (featured GitHub card)
    const connectButtons = screen.getAllByText('Connect');
    fireEvent.click(connectButtons[0]);

    await waitFor(() => {
      expect(mockAuthorize).toHaveBeenCalledWith('github', {
        redirect_after: 'http://localhost/',
      });
    });

    Object.defineProperty(window, 'location', { writable: true, value: originalLocation });
  });

  it('calls disconnect with confirm dialog', async () => {
    mockConfirm.mockResolvedValue(true);
    mockDisconnect.mockResolvedValue(undefined);
    mockListConnectors.mockResolvedValue({
      connectors: mockConnectors,
      total_count: mockConnectors.length,
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Disconnect').length).toBeGreaterThanOrEqual(1);
    });

    // Click first Disconnect button (featured Linear card)
    fireEvent.click(screen.getAllByText('Disconnect')[0]);

    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Disconnect Linear?',
          variant: 'danger',
        })
      );
    });
  });

  it('shows error state', async () => {
    mockListConnectors.mockRejectedValue(new Error('Network error'));
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('shows empty state when no connectors match filter', async () => {
    mockListConnectors.mockResolvedValue({ connectors: [], total_count: 0 });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('shows environment badge for connected connectors', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Development').length).toBeGreaterThan(0);
    });
  });

  it('shows promote button for connected dev connectors', async () => {
    renderComponent();
    await waitFor(() => {
      // Linear is connected in dev, so Staging promote button should appear
      expect(screen.getAllByText('Staging').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('calls promote API on promote click', async () => {
    mockPromote.mockResolvedValue({
      slug: 'linear',
      source_environment: 'dev',
      target_environment: 'staging',
      server_id: 'srv-2',
      server_name: 'linear-staging',
      credentials_cloned: true,
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByTitle('Promote to Staging').length).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(screen.getAllByTitle('Promote to Staging')[0]);

    await waitFor(() => {
      expect(mockPromote).toHaveBeenCalledWith('linear', {
        target_environment: 'staging',
        confirm: false,
      });
    });
  });

  it('renders environment filter dropdown', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('All environments')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page without crashing', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        await waitFor(() => {
          expect(screen.getByText('MCP Connectors')).toBeInTheDocument();
        });
      });
    }
  );
});
