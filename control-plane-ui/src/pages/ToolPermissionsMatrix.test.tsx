import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { ToolPermissionsMatrix } from './ToolPermissionsMatrix';
import { createAuthMock, renderWithProviders } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import { externalMcpServersService } from '../services/externalMcpServersApi';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
vi.mock('../services/api', () => ({
  apiService: {
    listToolPermissions: vi.fn(),
    upsertToolPermission: vi.fn(),
    deleteToolPermission: vi.fn(),
  },
}));
vi.mock('../services/externalMcpServersApi', () => ({
  externalMcpServersService: {
    listServers: vi.fn(),
    getServer: vi.fn(),
  },
}));

const mockServersResponse = {
  servers: [
    {
      id: 'srv-1',
      name: 'linear-mcp',
      display_name: 'Linear',
      base_url: 'https://mcp.linear.app',
      transport: 'sse' as const,
      auth_type: 'bearer_token' as const,
      enabled: true,
      health_status: 'healthy' as const,
      tools_count: 2,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  total_count: 1,
  page: 1,
  page_size: 100,
};

const mockServerDetail = {
  ...mockServersResponse.servers[0],
  tools: [
    {
      id: 't1',
      name: 'linear_create_issue',
      namespaced_name: 'linear_create_issue',
      description: 'Create a Linear issue',
      enabled: true,
      synced_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 't2',
      name: 'linear_list_issues',
      namespaced_name: 'linear_list_issues',
      description: 'List Linear issues',
      enabled: true,
      synced_at: '2026-01-01T00:00:00Z',
    },
  ],
};

const mockPermissions = {
  items: [
    {
      id: 'perm-1',
      tenant_id: 'test-tenant',
      mcp_server_id: 'srv-1',
      tool_name: 'linear_create_issue',
      allowed: false,
      created_by: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 100,
};

describe('ToolPermissionsMatrix', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('stoa-active-tenant', 'test-tenant');
    vi.mocked(externalMcpServersService.listServers).mockResolvedValue(mockServersResponse);
    vi.mocked(externalMcpServersService.getServer).mockResolvedValue(mockServerDetail);
    vi.mocked(apiService.listToolPermissions).mockResolvedValue(mockPermissions);
    vi.mocked(apiService.upsertToolPermission).mockResolvedValue(mockPermissions.items[0]);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin'])('%s can edit', (role) => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
    });

    it('renders page title', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      expect(screen.getByText('Tool Permissions')).toBeInTheDocument();
    });

    it('loads servers and tools', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      await waitFor(() => expect(screen.getByText('Linear')).toBeInTheDocument());
    });

    it('shows tool permissions when server is expanded', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      await waitFor(() => expect(screen.getByText('Linear')).toBeInTheDocument());

      // Expand the server
      fireEvent.click(screen.getByText('Linear'));

      await waitFor(() => {
        expect(screen.getByText('linear_create_issue')).toBeInTheDocument();
        expect(screen.getByText('linear_list_issues')).toBeInTheDocument();
      });
    });

    it('shows denied status for tools with allowed=false', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      await waitFor(() => expect(screen.getByText('Linear')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Linear'));

      await waitFor(() => {
        // linear_create_issue has allowed=false in mockPermissions
        expect(screen.getByText('Denied')).toBeInTheDocument();
        // linear_list_issues has no permission row → default allowed
        expect(screen.getByText('Allowed')).toBeInTheDocument();
      });
    });

    it('shows save and reset buttons', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      await waitFor(() => expect(screen.getByText('Linear')).toBeInTheDocument());
      expect(screen.getByText('Save Changes')).toBeInTheDocument();
      expect(screen.getByText('Reset')).toBeInTheDocument();
    });

    it('enables save button after toggling a tool', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      await waitFor(() => expect(screen.getByText('Linear')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Linear'));

      await waitFor(() => expect(screen.getByText('Allowed')).toBeInTheDocument());

      // Toggle the allowed tool to denied
      fireEvent.click(screen.getByText('Allowed'));

      // Save should now be enabled (no longer disabled)
      const saveBtn = screen.getByText('Save Changes');
      expect(saveBtn.closest('button')).not.toBeDisabled();
    });

    it('calls upsertToolPermission on save', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      await waitFor(() => expect(screen.getByText('Linear')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Linear'));

      await waitFor(() => expect(screen.getByText('Allowed')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Allowed'));

      fireEvent.click(screen.getByText('Save Changes'));

      await waitFor(() =>
        expect(apiService.upsertToolPermission).toHaveBeenCalledWith('test-tenant', {
          mcp_server_id: 'srv-1',
          tool_name: 'linear_list_issues',
          allowed: false,
        })
      );
    });

    it('shows bulk Allow all / Deny all buttons per server', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      await waitFor(() => expect(screen.getByText('Linear')).toBeInTheDocument());
      expect(screen.getByText('Allow all')).toBeInTheDocument();
      expect(screen.getByText('Deny all')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['devops', 'viewer'])('%s cannot edit', (role) => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
    });

    it('renders page in read-only mode', async () => {
      renderWithProviders(<ToolPermissionsMatrix />);
      expect(screen.getByText('Tool Permissions')).toBeInTheDocument();
      // No save/reset buttons for read-only users
      expect(screen.queryByText('Save Changes')).not.toBeInTheDocument();
    });
  });

  it('shows no-tenant message when no tenant selected', () => {
    localStorage.removeItem('stoa-active-tenant');
    const mock = createAuthMock('cpi-admin');
    vi.mocked(useAuth).mockReturnValue({
      ...mock,
      user: { ...mock.user, tenant_id: undefined },
    });
    renderWithProviders(<ToolPermissionsMatrix />);
    expect(screen.getByText(/No tenant selected/i)).toBeInTheDocument();
  });

  it('shows empty state when no servers have tools', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.mocked(externalMcpServersService.listServers).mockResolvedValue({
      servers: [],
      total_count: 0,
      page: 1,
      page_size: 100,
    });
    vi.mocked(apiService.listToolPermissions).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });

    renderWithProviders(<ToolPermissionsMatrix />);
    await waitFor(() =>
      expect(screen.getByText(/No MCP servers with tools found/i)).toBeInTheDocument()
    );
  });
});
