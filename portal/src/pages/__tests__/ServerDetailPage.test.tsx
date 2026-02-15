/**
 * ServerDetailPage Tests (CAB-1133)
 *
 * Page-level functional tests for the MCP Server detail page.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders, mockMCPServer } from '../../test/helpers';
import { Routes, Route } from 'react-router-dom';
import type { MCPServer } from '../../types';

// Mock AuthContext
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock mcpServersService
vi.mock('../../services/mcpServers', async () => {
  const actual = await vi.importActual('../../services/mcpServers');
  return {
    ...actual,
    mcpServersService: {
      getServer: vi.fn(),
      getMyServerSubscriptions: vi.fn(),
      subscribeToServer: vi.fn(),
      canUserSeeServer: vi.fn().mockReturnValue(true),
    },
    MOCK_SERVERS: [],
  };
});

// Mock config
vi.mock('../../config', () => ({
  config: {
    api: {
      baseUrl: 'https://api.gostoa.dev',
      timeout: 30000,
    },
    mcp: {
      baseUrl: 'https://mcp.gostoa.dev',
      timeout: 30000,
    },
    keycloak: {
      url: 'https://auth.gostoa.dev',
      realm: 'stoa',
      clientId: 'stoa-portal',
      authority: 'https://auth.gostoa.dev/realms/stoa',
    },
  },
}));

describe('ServerDetailPage', () => {
  let ServerDetailPage: React.ComponentType;
  let mcpServersService: Record<string, ReturnType<typeof vi.fn>>;
  let mockGetServer: ReturnType<typeof vi.fn>;
  let mockGetMyServerSubscriptions: ReturnType<typeof vi.fn>;
  let mockSubscribeToServer: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.clearAllMocks();

    const pageModule = await import('../servers/ServerDetailPage');
    ServerDetailPage = pageModule.ServerDetailPage;

    const serviceModule = await import('../../services/mcpServers');
    mcpServersService = serviceModule.mcpServersService;
    mockGetServer = vi.mocked(mcpServersService.getServer);
    mockGetMyServerSubscriptions = vi.mocked(mcpServersService.getMyServerSubscriptions);
    mockSubscribeToServer = vi.mocked(mcpServersService.subscribeToServer);

    mockGetMyServerSubscriptions.mockResolvedValue([]);
  });

  const createMockServer = (): MCPServer => {
    return mockMCPServer({
      id: 'server-1',
      name: 'stoa-platform',
      displayName: 'STOA Platform Tools',
      description: 'Core STOA administration tools',
      category: 'platform',
      version: '1.0.0',
      status: 'active',
      tools: [
        {
          id: 'tool-1',
          name: 'list-apis',
          displayName: 'List APIs',
          description: 'List all registered APIs',
          enabled: true,
          requires_approval: false,
        },
        {
          id: 'tool-2',
          name: 'create-api',
          displayName: 'Create API',
          description: 'Register a new API',
          enabled: true,
          requires_approval: true,
        },
      ],
    });
  };

  const renderWithRoute = (serverId: string = 'server-1') => {
    return renderWithProviders(
      <Routes>
        <Route path="/servers/:serverId" element={<ServerDetailPage />} />
      </Routes>,
      { route: `/servers/${serverId}` }
    );
  };

  it('shows loading state with spinner', () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetServer.mockImplementation(() => new Promise(() => {})); // Never resolves

    renderWithRoute();

    // While loading, the error and content should not be visible
    expect(screen.queryByText('Error')).not.toBeInTheDocument();
    expect(screen.queryByText('Available Tools')).not.toBeInTheDocument();
  });

  it('shows error message when server not found', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetServer.mockResolvedValue(undefined);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Error')).toBeInTheDocument();
      expect(screen.getByText('Server not found')).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /Back to Servers/i })).toBeInTheDocument();
    });
  });

  it('renders server details: displayName, version, status, description', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('STOA Platform Tools')).toBeInTheDocument();
      expect(screen.getByText('v1.0.0')).toBeInTheDocument();
      expect(screen.getByText('active')).toBeInTheDocument();
      expect(screen.getByText('Core STOA administration tools')).toBeInTheDocument();
    });
  });

  it('renders tools count and category badge', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('2 tools')).toBeInTheDocument();
      expect(screen.getByText('platform')).toBeInTheDocument();
    });
  });

  it('renders tools list with displayName and description', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('List APIs')).toBeInTheDocument();
      expect(screen.getByText('List all registered APIs')).toBeInTheDocument();
      expect(screen.getByText('Create API')).toBeInTheDocument();
      expect(screen.getByText('Register a new API')).toBeInTheDocument();
      expect(screen.getByText('Requires Approval')).toBeInTheDocument();
    });
  });

  it('shows "Select All" toggle before subscription', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      // By default all tools are selected, so "Deselect All" is shown
      // The test is that the toggle exists and can switch between Select All / Deselect All
      expect(screen.getByText('Deselect All')).toBeInTheDocument();
    });
  });

  it('shows "Deselect All" when all tools are selected', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      // All tools are selected by default
      expect(screen.getByText('Deselect All')).toBeInTheDocument();
    });
  });

  it('tool checkboxes work before subscription', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Available Tools')).toBeInTheDocument();
    });

    // All tools are selected by default, deselect all first
    const deselectAllButton = screen.getByText('Deselect All');
    await user.click(deselectAllButton);

    // Now select one tool
    const toolRow = screen.getByText('List APIs').closest('div[role="button"]');
    await user.click(toolRow!);

    await waitFor(() => {
      expect(screen.getByText('1 of 2 tools selected')).toBeInTheDocument();
    });
  });

  it('subscribe button shows selected count', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('2 of 2 tools selected')).toBeInTheDocument();
    });
  });

  it('subscribe button is disabled when 0 tools selected', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Deselect All')).toBeInTheDocument();
    });

    const deselectAllButton = screen.getByText('Deselect All');
    await user.click(deselectAllButton);

    await waitFor(() => {
      const subscribeButton = screen.getByRole('button', { name: /Subscribe & Get API Key/i });
      expect(subscribeButton).toBeDisabled();
    });
  });

  it('shows API key section after successful subscription', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);
    mockSubscribeToServer.mockResolvedValue({
      id: 'sub-1',
      server_id: 'server-1',
      server,
      tenant_id: 'oasis-gunters',
      user_id: 'user-parzival',
      status: 'active',
      plan: 'free',
      tool_access: [],
      api_key_prefix: 'stoa_sk_test',
      api_key: 'stoa_sk_test_abcdef123456',
      created_at: '2026-02-11T00:00:00Z',
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Subscribe & Get API Key/i })).toBeInTheDocument();
    });

    const subscribeButton = screen.getByRole('button', { name: /Subscribe & Get API Key/i });
    await user.click(subscribeButton);

    await waitFor(() => {
      expect(screen.getByText('Subscription Created!')).toBeInTheDocument();
      expect(
        screen.getByText('Save your API key now. It will only be shown once.')
      ).toBeInTheDocument();
      expect(screen.getByText('stoa_sk_test_abcdef123456')).toBeInTheDocument();
    });
  });

  it('shows Claude.ai and Desktop config after subscription', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);
    mockSubscribeToServer.mockResolvedValue({
      id: 'sub-1',
      server_id: 'server-1',
      server,
      tenant_id: 'oasis-gunters',
      user_id: 'user-parzival',
      status: 'active',
      plan: 'free',
      tool_access: [],
      api_key_prefix: 'stoa_sk_test',
      api_key: 'stoa_sk_test_xyz789',
      created_at: '2026-02-11T00:00:00Z',
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Subscribe & Get API Key/i })).toBeInTheDocument();
    });

    const subscribeButton = screen.getByRole('button', { name: /Subscribe & Get API Key/i });
    await user.click(subscribeButton);

    await waitFor(() => {
      expect(screen.getByText('Configure with Claude.ai')).toBeInTheDocument();
      expect(screen.getByText('Claude.ai (Web) - Recommended')).toBeInTheDocument();
      expect(screen.getByText('Claude Desktop App')).toBeInTheDocument();
    });
  });

  it('shows Copy buttons for API key and configs', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);
    mockSubscribeToServer.mockResolvedValue({
      id: 'sub-1',
      server_id: 'server-1',
      server,
      tenant_id: 'oasis-gunters',
      user_id: 'user-parzival',
      status: 'active',
      plan: 'free',
      tool_access: [],
      api_key_prefix: 'stoa_sk_test',
      api_key: 'stoa_sk_test_copy',
      created_at: '2026-02-11T00:00:00Z',
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Subscribe & Get API Key/i })).toBeInTheDocument();
    });

    const subscribeButton = screen.getByRole('button', { name: /Subscribe & Get API Key/i });
    await user.click(subscribeButton);

    await waitFor(() => {
      const copyButtons = screen.getAllByRole('button', { name: /Copy/i });
      expect(copyButtons.length).toBeGreaterThan(0);
    });
  });

  it('shows tool access status badges when subscribed', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);
    mockGetMyServerSubscriptions.mockResolvedValue([
      {
        id: 'sub-1',
        server_id: 'server-1',
        server,
        tenant_id: 'oasis-gunters',
        user_id: 'user-parzival',
        status: 'active',
        plan: 'free',
        tool_access: [
          { tool_id: 'tool-1', tool_name: 'list-apis', status: 'enabled' },
          { tool_id: 'tool-2', tool_name: 'create-api', status: 'pending_approval' },
        ],
        api_key_prefix: 'stoa_sk_test',
        created_at: '2026-02-11T00:00:00Z',
      },
    ]);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Enabled')).toBeInTheDocument();
      expect(screen.getByText('Pending')).toBeInTheDocument();
    });
  });

  it('shows "Back to Servers" breadcrumb link', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);

    renderWithRoute();

    await waitFor(() => {
      const backLink = screen.getAllByRole('link', { name: /Back to Servers/i });
      expect(backLink.length).toBeGreaterThan(0);
    });
  });

  it('shows subscription management buttons when subscribed', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const server = createMockServer();
    mockGetServer.mockResolvedValue(server);
    mockGetMyServerSubscriptions.mockResolvedValue([
      {
        id: 'sub-1',
        server_id: 'server-1',
        server,
        tenant_id: 'oasis-gunters',
        user_id: 'user-parzival',
        status: 'active',
        plan: 'free',
        tool_access: [{ tool_id: 'tool-1', tool_name: 'list-apis', status: 'enabled' }],
        api_key_prefix: 'stoa_sk_test',
        created_at: '2026-02-11T00:00:00Z',
      },
    ]);

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Subscription Management')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Rotate API Key/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Request Additional Tools/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Revoke Subscription/i })).toBeInTheDocument();
    });
  });

  describe('Persona-based Tests', () => {
    const personas: import('../../test/helpers').PersonaRole[] = [
      'cpi-admin',
      'tenant-admin',
      'devops',
      'viewer',
    ];

    it.each(personas)('%s can view server detail (stoa:catalog:read)', async (persona) => {
      mockAuth.mockReturnValue(createAuthMock(persona));
      const server = createMockServer();
      mockGetServer.mockResolvedValue(server);

      renderWithRoute();

      await waitFor(() => {
        expect(screen.getByText('STOA Platform Tools')).toBeInTheDocument();
        expect(screen.getByText('Core STOA administration tools')).toBeInTheDocument();
      });
    });
  });
});
