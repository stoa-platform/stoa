import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { PersonaRole } from '../../test/helpers';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';

const mockListConnectors = vi.fn();
const mockAuthorize = vi.fn();
const mockDisconnect = vi.fn();
const mockListServers = vi.fn();
const mockTestConnection = vi.fn();
const mockSyncTools = vi.fn();
const mockDeleteServer = vi.fn();
const mockCreateServer = vi.fn();

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../contexts/EnvironmentContext', () => ({
  useEnvironment: () => ({
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [],
    endpoints: null,
    switchEnvironment: vi.fn(),
    loading: false,
    error: null,
  }),
}));

vi.mock('../../config', () => ({
  config: {
    features: { enableMcpCatalog: true },
  },
}));

vi.mock('../../services/mcpConnectorsApi', () => ({
  mcpConnectorsService: {
    listConnectors: (...args: unknown[]) => mockListConnectors(...args),
    authorize: (...args: unknown[]) => mockAuthorize(...args),
    disconnect: (...args: unknown[]) => mockDisconnect(...args),
  },
}));

vi.mock('../../services/externalMcpServersApi', () => ({
  externalMcpServersService: {
    listServers: (...args: unknown[]) => mockListServers(...args),
    testConnection: (...args: unknown[]) => mockTestConnection(...args),
    syncTools: (...args: unknown[]) => mockSyncTools(...args),
    deleteServer: (...args: unknown[]) => mockDeleteServer(...args),
    createServer: (...args: unknown[]) => mockCreateServer(...args),
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

vi.mock('../ExternalMCPServers/ExternalMCPServerModal', () => ({
  ExternalMCPServerModal: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="server-modal">
      <button onClick={onClose}>Close</button>
    </div>
  ),
}));

import { MCPServersUnified } from './MCPServersUnified';

const mockConnectors = [
  {
    id: '1',
    slug: 'linear',
    display_name: 'Linear',
    description: 'Project management for modern teams',
    icon_url: 'https://example.com/linear.png',
    category: 'project_management',
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
    is_featured: false,
    enabled: true,
    sort_order: 2,
    is_connected: false,
    connected_server_id: null,
    connection_health: null,
  },
];

const mockServers = [
  {
    id: 'srv-1',
    name: 'my-linear',
    display_name: 'My Linear',
    transport: 'sse',
    url: 'https://mcp.linear.app',
    auth_type: 'oauth2',
    icon: null,
    enabled: true,
    health_status: 'healthy' as const,
    tools_count: 12,
    tool_prefix: 'linear',
    sync_error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'srv-2',
    name: 'custom-api',
    display_name: 'Custom API',
    transport: 'http',
    url: 'https://mcp.example.com',
    auth_type: 'api_key',
    icon: null,
    enabled: true,
    health_status: 'unknown' as const,
    tools_count: 0,
    tool_prefix: null,
    sync_error: null,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
];

function renderComponent(initialEntries: string[] = ['/mcp-servers']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <MCPServersUnified />
    </MemoryRouter>
  );
}

describe('MCPServersUnified', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockListConnectors.mockResolvedValue({
      connectors: mockConnectors,
      total_count: mockConnectors.length,
    });
    mockListServers.mockResolvedValue({
      servers: mockServers,
      total_count: mockServers.length,
    });
  });

  it('renders page header and both tabs', async () => {
    renderComponent();
    expect(screen.getByText('MCP Servers')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Catalog/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Custom Servers/i })).toBeInTheDocument();
  });

  it('renders Catalog tab by default with connector cards', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('GitHub').length).toBeGreaterThanOrEqual(1);
  });

  it('opens Custom Servers tab when ?tab=custom', async () => {
    renderComponent(['/mcp-servers?tab=custom']);
    await waitFor(() => {
      expect(screen.getByText('My Linear')).toBeInTheDocument();
    });
    expect(screen.getByText('Custom API')).toBeInTheDocument();
  });

  it('switches to Custom Servers tab on click', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(screen.getByRole('button', { name: /Custom Servers/i }));

    await waitFor(() => {
      expect(screen.getByText('My Linear')).toBeInTheDocument();
    });
    expect(screen.getByText('Custom API')).toBeInTheDocument();
  });

  it('shows Add Server button only on Custom tab', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByText('Add Server')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Custom Servers/i }));
    await waitFor(() => {
      expect(screen.getByText('Add Server')).toBeInTheDocument();
    });
  });

  it('category filter works in Catalog tab', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Linear').length).toBeGreaterThanOrEqual(1);
    });
    // Filter by Development — only GitHub should remain
    fireEvent.click(screen.getByRole('button', { name: 'Development' }));
    expect(screen.getByText('GitHub')).toBeInTheDocument();
    expect(screen.queryByText('Linear')).not.toBeInTheDocument();
  });

  it('calls authorize API on Connect click', async () => {
    mockAuthorize.mockResolvedValue({ authorize_url: 'https://auth.example.com', state: 'xyz' });

    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, href: 'http://localhost/' },
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('GitHub').length).toBeGreaterThanOrEqual(1);
    });

    const connectButtons = screen.getAllByText('Connect');
    fireEvent.click(connectButtons[0]);

    await waitFor(() => {
      expect(mockAuthorize).toHaveBeenCalledWith('github', {
        redirect_after: 'http://localhost/',
      });
    });

    Object.defineProperty(window, 'location', { writable: true, value: originalLocation });
  });

  it('Test button calls testConnection on Custom tab', async () => {
    mockTestConnection.mockResolvedValue({
      success: true,
      tools_discovered: 12,
      latency_ms: 42,
    });

    renderComponent(['/mcp-servers?tab=custom']);
    await waitFor(() => {
      expect(screen.getByText('My Linear')).toBeInTheDocument();
    });

    const testButtons = screen.getAllByText('Test');
    fireEvent.click(testButtons[0]);

    await waitFor(() => {
      expect(mockTestConnection).toHaveBeenCalledWith('srv-1');
    });
  });

  it('shows error state on Catalog tab', async () => {
    mockListConnectors.mockRejectedValue(new Error('Network error'));
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('shows error state on Custom Servers tab', async () => {
    mockListServers.mockRejectedValue(new Error('Server error'));
    renderComponent(['/mcp-servers?tab=custom']);
    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });

  it('shows empty state when no custom servers', async () => {
    mockListServers.mockResolvedValue({ servers: [], total_count: 0 });
    renderComponent(['/mcp-servers?tab=custom']);
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page without crashing', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        await waitFor(() => {
          expect(screen.getByText('MCP Servers')).toBeInTheDocument();
        });
      });
    }
  );
});
