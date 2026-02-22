/**
 * MCPServersPage Tests (CAB-1133)
 *
 * Page-level functional tests for the MCP Servers listing page.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders, mockMCPServer } from '../../test/helpers';
import type { MCPServer } from '../../types';

// Mock AuthContext — use factory function for per-test persona switching
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock mcpServersService as module
vi.mock('../../services/mcpServers', async () => {
  const actual = await vi.importActual('../../services/mcpServers');
  return {
    ...actual,
    mcpServersService: {
      getVisibleServers: vi.fn(),
      filterServersByRole: vi.fn(),
      getMyServerSubscriptions: vi.fn(),
      canUserSeeServer: (actual as Record<string, unknown>).canUserSeeServer,
    },
  };
});

// Mock ServerCardSkeletonGrid
vi.mock('../../components/skeletons', () => ({
  ServerCardSkeletonGrid: ({ count }: { count: number }) => (
    <div data-testid="server-skeleton-grid">Loading {count} servers...</div>
  ),
}));

describe('MCPServersPage', () => {
  let MCPServersPage: React.ComponentType;
  let mcpServersService: Record<string, ReturnType<typeof vi.fn>>;
  let mockGetVisibleServers: ReturnType<typeof vi.fn>;
  let mockFilterServersByRole: ReturnType<typeof vi.fn>;
  let mockGetMyServerSubscriptions: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.clearAllMocks();

    // Dynamic import to get mocked module
    const pageModule = await import('../servers/MCPServersPage');
    MCPServersPage = pageModule.MCPServersPage;

    const serviceModule = await import('../../services/mcpServers');
    mcpServersService = serviceModule.mcpServersService;
    mockGetVisibleServers = vi.mocked(mcpServersService.getVisibleServers);
    mockFilterServersByRole = vi.mocked(mcpServersService.filterServersByRole);
    mockGetMyServerSubscriptions = vi.mocked(mcpServersService.getMyServerSubscriptions);

    // Default mocks
    mockGetMyServerSubscriptions.mockResolvedValue([]);
    mockGetVisibleServers.mockResolvedValue([]); // Default to empty array
    mockFilterServersByRole.mockReturnValue([]);
  });

  const createMockServers = (): MCPServer[] => [
    mockMCPServer({
      id: 'server-platform',
      name: 'stoa-platform',
      displayName: 'STOA Platform Tools',
      category: 'platform',
      tools: [
        {
          id: 'tool-1',
          name: 'list-apis',
          displayName: 'List APIs',
          description: 'List all APIs',
          enabled: true,
          requires_approval: false,
        },
        {
          id: 'tool-2',
          name: 'create-api',
          displayName: 'Create API',
          description: 'Register API',
          enabled: true,
          requires_approval: true,
        },
      ],
      visibility: { roles: ['cpi-admin', 'tenant-admin', 'devops'], public: false },
    }),
    mockMCPServer({
      id: 'server-tenant',
      name: 'crm-apis',
      displayName: 'CRM Integration',
      category: 'tenant',
      tools: [
        {
          id: 'tool-3',
          name: 'customer-search',
          displayName: 'Search Customers',
          description: 'Search customers',
          enabled: true,
          requires_approval: false,
        },
      ],
      visibility: { public: true },
    }),
    mockMCPServer({
      id: 'server-public',
      name: 'public-tools',
      displayName: 'Public Tools',
      category: 'public',
      tools: [
        {
          id: 'tool-4',
          name: 'weather',
          displayName: 'Weather',
          description: 'Get weather',
          enabled: true,
          requires_approval: false,
        },
      ],
      visibility: { public: true },
    }),
  ];

  it('renders "AI Tools" heading', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetVisibleServers.mockResolvedValue([]);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('AI Tools')).toBeInTheDocument();
    });
  });

  it('shows loading state with skeleton grid', () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetVisibleServers.mockImplementation(() => new Promise(() => {})); // Never resolves

    renderWithProviders(<MCPServersPage />);

    expect(screen.getByTestId('server-skeleton-grid')).toBeInTheDocument();
    expect(screen.getByText(/Loading 6 servers/)).toBeInTheDocument();
  });

  it('shows error state with "Try Again" button', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetVisibleServers.mockRejectedValue(new Error('Network error'));

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load servers')).toBeInTheDocument();
      expect(screen.getByText('Network error')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Try Again/i })).toBeInTheDocument();
    });
  });

  it('shows empty state when no servers match filters', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetVisibleServers.mockResolvedValue([]);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('No AI Tools Found')).toBeInTheDocument();
    });
  });

  it('admin users (cpi-admin) see "Admin Access" notice and "Platform Tools" category tab', async () => {
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('Admin Access')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Platform Tools/i })).toBeInTheDocument();
    });
  });

  it('admin users (tenant-admin) see "Admin Access" notice and "Platform Tools" category tab', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('Admin Access')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Platform Tools/i })).toBeInTheDocument();
    });
  });

  it('admin users (devops) see "Admin Access" notice and "Platform Tools" category tab', async () => {
    mockAuth.mockReturnValue(createAuthMock('devops'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('Admin Access')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Platform Tools/i })).toBeInTheDocument();
    });
  });

  it('viewer does NOT see "Admin Access" notice or "Platform Tools" category tab', async () => {
    mockAuth.mockReturnValue(createAuthMock('viewer'));
    const servers = createMockServers().filter((s) => s.category !== 'platform');
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.queryByText('Admin Access')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Platform Tools/i })).not.toBeInTheDocument();
    });
  });

  it('renders category tabs: All, Platform (admin), Tenant, Public with counts', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /All Tools/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Platform Tools/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Tenant Tools/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Public Tools/i })).toBeInTheDocument();

      // Check counts - "3" appears in the All Tools tab
      expect(screen.getByText('3')).toBeInTheDocument();
    });
  });

  it('search input exists with placeholder "Search AI tools..."', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetVisibleServers.mockResolvedValue([]);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('Search AI tools...');
      expect(searchInput).toBeInTheDocument();
    });
  });

  it('server cards show displayName, description, tools count', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      // Check server names via links (more specific than text search)
      expect(screen.getByRole('link', { name: /STOA Platform Tools/i })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /CRM Integration/i })).toBeInTheDocument();

      // Check tools count
      expect(screen.getByText('2 tools')).toBeInTheDocument(); // Platform server
      expect(screen.getAllByText('1 tools')).toHaveLength(2); // CRM + Public servers
    });
  });

  it('shows "Subscribed" badge on subscribed servers', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);
    mockGetMyServerSubscriptions.mockResolvedValue([
      {
        id: 'sub-1',
        server_id: 'server-tenant',
        server: servers[1],
        tenant_id: 'oasis-gunters',
        user_id: 'user-parzival',
        status: 'active',
        plan: 'free',
        tool_access: [],
        api_key_prefix: 'stoa_sk_test',
        created_at: '2026-01-20T00:00:00Z',
      },
    ]);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('Subscribed')).toBeInTheDocument();
    });
  });

  it('refresh button exists and triggers reload', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const servers = createMockServers();
    // First call resolves (initial load), second call never resolves (refresh stays loading)
    mockGetVisibleServers
      .mockResolvedValueOnce(servers)
      .mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Refresh/i })).toBeInTheDocument();
    });

    const refreshButton = screen.getByRole('button', { name: /Refresh/i });
    await user.click(refreshButton);

    // Should trigger loading state
    await waitFor(() => {
      expect(screen.getByTestId('server-skeleton-grid')).toBeInTheDocument();
    });
  });

  it('filters servers by search query', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByText('STOA Platform Tools')).toBeInTheDocument();
      expect(screen.getByText('CRM Integration')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search AI tools...');
    await user.type(searchInput, 'CRM');

    await waitFor(() => {
      expect(screen.getByText('CRM Integration')).toBeInTheDocument();
      expect(screen.queryByText('STOA Platform Tools')).not.toBeInTheDocument();
    });
  });

  it('filters servers by category tab', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const servers = createMockServers();
    mockGetVisibleServers.mockResolvedValue(servers);

    renderWithProviders(<MCPServersPage />);

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /STOA Platform Tools/i })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /CRM Integration/i })).toBeInTheDocument();
    });

    const tenantTab = screen.getByRole('button', { name: /Tenant Tools/i });
    await user.click(tenantTab);

    await waitFor(() => {
      // After clicking Tenant tab, only tenant category servers should be visible
      expect(screen.getByRole('link', { name: /CRM Integration/i })).toBeInTheDocument();
      // Platform server link should not be visible
      expect(screen.queryByRole('link', { name: /STOA Platform Tools/i })).not.toBeInTheDocument();
    });
  });
});
