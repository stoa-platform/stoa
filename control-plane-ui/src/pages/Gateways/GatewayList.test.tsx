import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['tenants:read', 'apis:read', 'apps:read', 'audit:read', 'admin:servers'],
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

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayInstances: vi.fn().mockResolvedValue({
      items: [
        {
          id: 'gw-1',
          name: 'stoa-edge-mcp-1',
          display_name: 'STOA Edge MCP Gateway',
          gateway_type: 'stoa_edge_mcp',
          environment: 'dev',
          base_url: 'https://mcp.gostoa.dev',
          auth_config: {},
          status: 'online',
          capabilities: ['mcp', 'openapi', 'rate_limiting'],
          tags: ['production'],
          mode: 'edge-mcp',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-15T00:00:00Z',
        },
        {
          id: 'gw-2',
          name: 'webmethods-prod',
          display_name: 'webMethods Production',
          gateway_type: 'webmethods',
          environment: 'prod',
          base_url: 'https://wm.example.com',
          auth_config: {},
          status: 'degraded',
          capabilities: ['rest', 'soap'],
          tags: ['legacy'],
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-10T00:00:00Z',
        },
      ],
      total: 2,
    }),
    checkGatewayHealth: vi.fn().mockResolvedValue({ status: 'online' }),
    deleteGatewayInstance: vi.fn().mockResolvedValue(undefined),
    registerGateway: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { GatewayList } from './GatewayList';

function renderGatewayList() {
  return render(
    <MemoryRouter>
      <GatewayList />
    </MemoryRouter>
  );
}

describe('GatewayList', () => {
  it('renders gateway display names', async () => {
    renderGatewayList();
    expect(await screen.findByText('STOA Edge MCP Gateway')).toBeInTheDocument();
    expect(screen.getByText('webMethods Production')).toBeInTheDocument();
  });

  it('renders gateway status badges', async () => {
    renderGatewayList();
    expect(await screen.findByText('online')).toBeInTheDocument();
    expect(screen.getByText('degraded')).toBeInTheDocument();
  });

  it('renders the mode filter dropdown', async () => {
    renderGatewayList();
    // The option text includes count: "All Modes (N)"
    expect(await screen.findByText(/All Modes/)).toBeInTheDocument();
  });

  it('renders gateway environment labels', async () => {
    renderGatewayList();
    expect(await screen.findByText('dev')).toBeInTheDocument();
    expect(screen.getByText('prod')).toBeInTheDocument();
  });

  it('renders the Edge MCP mode badge', async () => {
    renderGatewayList();
    expect(await screen.findByText('Edge MCP')).toBeInTheDocument();
  });

  it('renders the gateway type labels', async () => {
    renderGatewayList();
    expect(await screen.findByText('STOA Edge MCP')).toBeInTheDocument();
    expect(screen.getByText('webMethods')).toBeInTheDocument();
  });

  it('renders gateway base URLs', async () => {
    renderGatewayList();
    expect(await screen.findByText('https://mcp.gostoa.dev')).toBeInTheDocument();
    expect(screen.getByText('https://wm.example.com')).toBeInTheDocument();
  });
});
