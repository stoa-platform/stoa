import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// Mock AuthContext
vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: { id: 'user-admin', email: 'parzival@oasis.gg', name: 'Parzival', roles: ['cpi-admin'], tenant_id: 'oasis-gunters', permissions: ['tenants:read'] },
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: vi.fn(() => true),
    hasRole: vi.fn(() => true),
  })),
}));

// Mock errorSnapshotsService
const mockGetSnapshots = vi.fn().mockResolvedValue({
  snapshots: [
    {
      id: 'snap-1',
      error_type: 'server_timeout',
      error_message: 'Connection timed out after 30s',
      response_status: 504,
      mcp_server_name: 'weather-api',
      tool_name: 'get_weather',
      total_cost_usd: 0.05,
      tokens_wasted: 1200,
      resolution_status: 'unresolved',
      timestamp: '2024-01-15T10:00:00Z',
    },
  ],
  total: 1,
  has_next: false,
});
const mockGetStats = vi.fn().mockResolvedValue({
  total: 15,
  total_cost_usd: 1.25,
  avg_cost_usd: 0.083,
  total_tokens_wasted: 18000,
  resolution_stats: { unresolved: 5, investigating: 3, resolved: 6, ignored: 1 },
});
const mockGetFilters = vi.fn().mockResolvedValue({
  error_types: ['server_timeout', 'tool_not_found'],
  servers: ['weather-api', 'translate-api'],
  resolution_statuses: ['unresolved', 'investigating', 'resolved', 'ignored'],
});

vi.mock('../services/errorSnapshotsApi', () => ({
  errorSnapshotsService: {
    getSnapshots: (...args: unknown[]) => mockGetSnapshots(...args),
    getStats: (...args: unknown[]) => mockGetStats(...args),
    getFilters: (...args: unknown[]) => mockGetFilters(...args),
    getSnapshot: vi.fn().mockResolvedValue(null),
    updateResolution: vi.fn().mockResolvedValue({}),
    generateReplay: vi.fn().mockResolvedValue({ curl_command: 'curl ...' }),
  },
}));

// Mock config
vi.mock('../config', () => ({
  config: {
    services: {
      mcpGateway: { url: 'https://mcp.gostoa.dev' },
    },
  },
}));

import ErrorSnapshots from './ErrorSnapshots';

function renderComponent() {
  return render(<ErrorSnapshots />);
}

describe('ErrorSnapshots', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'MCP Error Snapshots' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(await screen.findByText('Time-travel debugging for MCP Gateway errors')).toBeInTheDocument();
  });

  it('shows stats cards after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Total Errors')).toBeInTheDocument();
    });
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('Total Cost')).toBeInTheDocument();
    expect(screen.getByText('Tokens Wasted')).toBeInTheDocument();
    // 'Resolved' appears in both stats card and filter dropdown
    expect(screen.getAllByText('Resolved').length).toBeGreaterThanOrEqual(1);
  });

  it('shows error snapshots list', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Connection timed out after 30s')).toBeInTheDocument();
    });
    // 'Server Timeout' appears in snapshot row and filter dropdown
    expect(screen.getAllByText('Server Timeout').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('504')).toBeInTheDocument();
  });

  it('shows server and tool names in snapshot row', async () => {
    renderComponent();
    await waitFor(() => {
      // 'weather-api' appears in snapshot row and filter dropdown
      expect(screen.getAllByText('weather-api').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByText('get_weather')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    renderComponent();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('shows auto-refresh checkbox', async () => {
    renderComponent();
    expect(await screen.findByText('Auto-refresh (10s)')).toBeInTheDocument();
  });

  it('shows filter dropdowns', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('All Error Types')).toBeInTheDocument();
    });
    expect(screen.getByText('All Servers')).toBeInTheDocument();
    expect(screen.getByText('All Statuses')).toBeInTheDocument();
  });

  it('shows search input', async () => {
    renderComponent();
    expect(await screen.findByPlaceholderText('Search errors...')).toBeInTheDocument();
  });

  it('shows snapshot count in header', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Error Snapshots (1)')).toBeInTheDocument();
    });
  });

  it('shows resolution status badge', async () => {
    renderComponent();
    await waitFor(() => {
      // 'Unresolved' appears in badge and filter dropdown
      expect(screen.getAllByText('Unresolved').length).toBeGreaterThanOrEqual(1);
    });
  });
});
