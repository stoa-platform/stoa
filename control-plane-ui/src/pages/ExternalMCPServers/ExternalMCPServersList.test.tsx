import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['admin:servers'],
    },
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: vi.fn(() => true),
    hasRole: vi.fn(() => true),
  })),
}));

// Mock externalMcpServersService
const mockListServers = vi.fn().mockResolvedValue({
  servers: [
    {
      id: 'srv-1',
      name: 'linear-mcp',
      display_name: 'Linear',
      url: 'https://mcp.linear.app',
      transport: 'sse',
      auth_type: 'bearer_token',
      enabled: true,
      health_status: 'healthy',
      tools_count: 12,
      tool_prefix: 'linear',
      icon: null,
      sync_error: null,
    },
    {
      id: 'srv-2',
      name: 'github-mcp',
      display_name: 'GitHub',
      url: 'https://mcp.github.com',
      transport: 'http',
      auth_type: 'oauth2',
      enabled: false,
      health_status: 'unhealthy',
      tools_count: 5,
      tool_prefix: 'gh',
      icon: null,
      sync_error: 'Connection refused',
    },
  ],
});

vi.mock('../../services/externalMcpServersApi', () => ({
  externalMcpServersService: {
    listServers: (...args: unknown[]) => mockListServers(...args),
    createServer: vi.fn().mockResolvedValue({}),
    testConnection: vi
      .fn()
      .mockResolvedValue({ success: true, tools_discovered: 5, latency_ms: 120 }),
    syncTools: vi.fn().mockResolvedValue({ synced_count: 5, removed_count: 0 }),
    deleteServer: vi.fn().mockResolvedValue({}),
  },
}));

// Mock shared components
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(false), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

// Mock ExternalMCPServerModal
vi.mock('./ExternalMCPServerModal', () => ({
  ExternalMCPServerModal: () => <div data-testid="create-modal">Create Modal</div>,
}));

import { ExternalMCPServersList } from './ExternalMCPServersList';

function renderComponent() {
  return render(
    <MemoryRouter>
      <ExternalMCPServersList />
    </MemoryRouter>
  );
}

describe('ExternalMCPServersList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(
      await screen.findByRole('heading', { name: 'External MCP Servers' })
    ).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(await screen.findByText(/Register external MCP servers/)).toBeInTheDocument();
  });

  it('shows server cards after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Linear')).toBeInTheDocument();
    });
    expect(screen.getByText('GitHub')).toBeInTheDocument();
  });

  it('shows server names in mono font', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('linear-mcp')).toBeInTheDocument();
    });
    expect(screen.getByText('github-mcp')).toBeInTheDocument();
  });

  it('shows health status badges', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Healthy').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('Unhealthy').length).toBeGreaterThanOrEqual(1);
  });

  it('shows transport type', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('SSE')).toBeInTheDocument();
    });
    expect(screen.getByText('HTTP')).toBeInTheDocument();
  });

  it('shows tools count', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('12')).toBeInTheDocument();
    });
  });

  it('shows enabled/disabled status', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Enabled')).toBeInTheDocument();
    });
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });

  it('shows sync error when present', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Connection refused')).toBeInTheDocument();
    });
  });

  it('shows action buttons for each server', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Test').length).toBe(2);
    });
    expect(screen.getAllByText('Sync').length).toBe(2);
    expect(screen.getAllByText('View').length).toBe(2);
  });

  it('shows Add Server button', async () => {
    renderComponent();
    expect(await screen.findByText('Add Server')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    renderComponent();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });
});
