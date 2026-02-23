/**
 * My MCP Servers Page Tests (CAB-1319)
 *
 * Persona-based tests covering RBAC visibility and core interactions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders, type PersonaRole } from '../../test/helpers';
import { MyMCPServersPage } from '../servers/MyMCPServersPage';

// ============ Mocks ============

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../services/tenantMcpServers', () => ({
  tenantMcpServersService: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    testConnection: vi.fn(),
    syncTools: vi.fn(),
    toggleTool: vi.fn(),
  },
}));

import { useAuth } from '../../contexts/AuthContext';
import { tenantMcpServersService } from '../../services/tenantMcpServers';

const mockUseAuth = vi.mocked(useAuth);
const mockService = vi.mocked(tenantMcpServersService);

// ============ Test Data ============

function mockServer(overrides: Record<string, unknown> = {}) {
  return {
    id: 'srv-1',
    name: 'linear',
    display_name: 'Linear',
    description: 'Linear issue tracking integration',
    icon: null,
    base_url: 'https://mcp.linear.app/sse',
    transport: 'sse' as const,
    auth_type: 'bearer_token' as const,
    has_credentials: true,
    tool_prefix: 'linear',
    enabled: true,
    health_status: 'healthy' as const,
    last_health_check: '2026-02-23T10:00:00Z',
    last_sync_at: '2026-02-23T10:00:00Z',
    sync_error: null,
    tools_count: 3,
    created_at: '2026-02-20T10:00:00Z',
    updated_at: '2026-02-23T10:00:00Z',
    ...overrides,
  };
}

function mockServerDetail(overrides: Record<string, unknown> = {}) {
  return {
    ...mockServer(overrides),
    tools: [
      {
        id: 'tool-1',
        name: 'create_issue',
        namespaced_name: 'linear__create_issue',
        display_name: 'Create Issue',
        description: 'Create a new issue in Linear',
        input_schema: null,
        enabled: true,
        synced_at: '2026-02-23T10:00:00Z',
      },
      {
        id: 'tool-2',
        name: 'list_issues',
        namespaced_name: 'linear__list_issues',
        display_name: 'List Issues',
        description: 'List issues in a project',
        input_schema: null,
        enabled: false,
        synced_at: '2026-02-23T10:00:00Z',
      },
    ],
  };
}

const defaultListResponse = {
  servers: [
    mockServer(),
    mockServer({ id: 'srv-2', name: 'github', display_name: 'GitHub', tools_count: 5 }),
  ],
  total_count: 2,
  page: 1,
  page_size: 20,
};

// ============ Setup ============

beforeEach(() => {
  vi.clearAllMocks();
  mockService.list.mockResolvedValue(defaultListResponse);
  mockService.get.mockResolvedValue(mockServerDetail());
  mockService.testConnection.mockResolvedValue({
    success: true,
    latency_ms: 42,
    error: null,
    server_info: null,
    tools_discovered: 3,
  });
  mockService.syncTools.mockResolvedValue({
    synced_count: 3,
    removed_count: 0,
    tools: [],
  });
  mockService.delete.mockResolvedValue(undefined);
  mockService.toggleTool.mockResolvedValue({
    id: 'tool-1',
    name: 'create_issue',
    namespaced_name: 'linear__create_issue',
    display_name: 'Create Issue',
    description: 'Create a new issue in Linear',
    input_schema: null,
    enabled: false,
    synced_at: '2026-02-23T10:00:00Z',
  });
});

// ============ Persona Tests ============

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'MyMCPServersPage — %s',
  (role) => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue(createAuthMock(role));
    });

    it('renders page title and server list', async () => {
      renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

      expect(screen.getByText('My MCP Servers')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText('Linear')).toBeInTheDocument();
        expect(screen.getByText('GitHub')).toBeInTheDocument();
      });
    });

    it('shows search input', () => {
      renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });
      expect(screen.getByPlaceholderText('Search servers...')).toBeInTheDocument();
    });

    if (role === 'cpi-admin' || role === 'tenant-admin') {
      it('shows Register Server button for write users', async () => {
        renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });
        await waitFor(() => {
          expect(screen.getByTestId('register-server-btn')).toBeInTheDocument();
        });
      });
    }

    if (role === 'devops' || role === 'viewer') {
      it('hides Register Server button for non-write users', async () => {
        renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });
        await waitFor(() => {
          expect(screen.getByText('Linear')).toBeInTheDocument();
        });
        expect(screen.queryByTestId('register-server-btn')).not.toBeInTheDocument();
      });
    }
  }
);

// ============ Interaction Tests ============

describe('MyMCPServersPage — interactions', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('filters servers by search query', async () => {
    const user = userEvent.setup();
    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('Linear')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText('Search servers...'), 'github');

    expect(screen.queryByText('Linear')).not.toBeInTheDocument();
    expect(screen.getByText('GitHub')).toBeInTheDocument();
  });

  it('expands server to show detail and tools', async () => {
    const user = userEvent.setup();
    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('Linear')).toBeInTheDocument();
    });

    // Click to expand
    await user.click(screen.getByText('Linear'));

    await waitFor(() => {
      expect(screen.getByText('Create Issue')).toBeInTheDocument();
      expect(screen.getByText('List Issues')).toBeInTheDocument();
    });

    expect(mockService.get).toHaveBeenCalledWith('oasis-gunters', 'srv-1');
  });

  it('shows empty state when no servers exist', async () => {
    mockService.list.mockResolvedValue({
      servers: [],
      total_count: 0,
      page: 1,
      page_size: 20,
    });

    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('No MCP Servers Registered')).toBeInTheDocument();
    });

    expect(screen.getByTestId('register-server-empty-btn')).toBeInTheDocument();
  });

  it('handles error state', async () => {
    mockService.list.mockRejectedValue(new Error('Network error'));

    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('shows health status badges', async () => {
    mockService.list.mockResolvedValue({
      servers: [
        mockServer({ health_status: 'healthy' }),
        mockServer({ id: 'srv-2', display_name: 'Unhealthy Server', health_status: 'unhealthy' }),
      ],
      total_count: 2,
      page: 1,
      page_size: 20,
    });

    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('healthy')).toBeInTheDocument();
      expect(screen.getByText('unhealthy')).toBeInTheDocument();
    });
  });
});

// ============ RBAC Action Tests ============

describe('MyMCPServersPage — RBAC actions', () => {
  it('tenant-admin sees delete and sync buttons in expanded view', async () => {
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
    const user = userEvent.setup();
    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('Linear')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Linear'));

    await waitFor(() => {
      expect(screen.getByText('Delete')).toBeInTheDocument();
      expect(screen.getByText('Sync Tools')).toBeInTheDocument();
      expect(screen.getByText('Test Connection')).toBeInTheDocument();
    });
  });

  it('devops sees test button but not delete/sync', async () => {
    mockUseAuth.mockReturnValue(createAuthMock('devops'));
    const user = userEvent.setup();
    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('Linear')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Linear'));

    await waitFor(() => {
      expect(screen.getByText('Test Connection')).toBeInTheDocument();
    });
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
    expect(screen.queryByText('Sync Tools')).not.toBeInTheDocument();
  });

  it('viewer sees no action buttons in expanded view', async () => {
    mockUseAuth.mockReturnValue(createAuthMock('viewer'));
    const user = userEvent.setup();
    renderWithProviders(<MyMCPServersPage />, { route: '/my-servers' });

    await waitFor(() => {
      expect(screen.getByText('Linear')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Linear'));

    await waitFor(() => {
      expect(screen.getByText('Create Issue')).toBeInTheDocument();
    });
    expect(screen.queryByText('Test Connection')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
    expect(screen.queryByText('Sync Tools')).not.toBeInTheDocument();
  });
});
