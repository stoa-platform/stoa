import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock AuthContext
vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['tenants:read', 'apis:read'],
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

// Mock api service
const mockGetTraces = vi.fn().mockResolvedValue({ traces: [] });
const mockGetTraceStats = vi.fn().mockResolvedValue({
  total: 42,
  success_rate: 95.2,
  avg_duration_ms: 1250,
  by_status: { success: 40, failed: 2, pending: 0, in_progress: 0, skipped: 0 },
});
const mockGetTenants = vi.fn().mockResolvedValue([
  {
    id: 'oasis-gunters',
    name: 'oasis-gunters',
    display_name: 'Oasis Gunters',
    status: 'active',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
]);
const mockGetApis = vi.fn().mockResolvedValue([]);
const mockGetDeployments = vi.fn().mockResolvedValue([]);

vi.mock('../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    getTraces: (...args: unknown[]) => mockGetTraces(...args),
    getTraceStats: (...args: unknown[]) => mockGetTraceStats(...args),
    getTrace: vi.fn().mockResolvedValue(null),
    getTenants: (...args: unknown[]) => mockGetTenants(...args),
    getApis: (...args: unknown[]) => mockGetApis(...args),
    getDeployments: (...args: unknown[]) => mockGetDeployments(...args),
    rollbackDeployment: vi.fn().mockResolvedValue({}),
  },
}));

// Mock config
vi.mock('../config', () => ({
  config: {
    api: { baseUrl: 'https://api.gostoa.dev' },
    services: {
      gitlab: { url: 'https://gitlab.example.com' },
      awx: {
        url: 'https://awx.example.com',
        getJobUrl: (id: string) => `https://awx.example.com/#/jobs/${id}`,
      },
    },
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
  EmptyState: ({ description }: { description: string }) => (
    <div data-testid="empty-state">{description}</div>
  ),
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton">Loading...</div>,
}));

import Deployments from './Deployments';

function renderComponent() {
  return render(
    <MemoryRouter>
      <Deployments />
    </MemoryRouter>
  );
}

describe('Deployments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTraces.mockResolvedValue({ traces: [] });
    mockGetTraceStats.mockResolvedValue({
      total: 42,
      success_rate: 95.2,
      avg_duration_ms: 1250,
      by_status: { success: 40, failed: 2, pending: 0, in_progress: 0, skipped: 0 },
    });
  });

  it('renders the Deployments heading', () => {
    renderComponent();
    expect(screen.getByRole('heading', { name: 'Deployments' })).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderComponent();
    expect(
      screen.getByText('GitOps pipeline monitoring and deployment history')
    ).toBeInTheDocument();
  });

  it('renders the three tab buttons', () => {
    renderComponent();
    expect(screen.getByText('Pipeline Traces')).toBeInTheDocument();
    expect(screen.getByText('Deployment History')).toBeInTheDocument();
    expect(screen.getByText('GitLab Config')).toBeInTheDocument();
  });

  it('shows Pipeline Traces tab content by default', async () => {
    renderComponent();
    expect(await screen.findByText('No pipeline traces yet')).toBeInTheDocument();
  });

  it('shows stats when trace data loads', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Total Pipelines')).toBeInTheDocument();
    });
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('95.2%')).toBeInTheDocument();
  });

  it('switches to GitLab Config tab', async () => {
    renderComponent();
    const configTab = screen.getByText('GitLab Config');
    fireEvent.click(configTab);
    expect(screen.getByText('GitOps Integration')).toBeInTheDocument();
    expect(screen.getByText('Repository Structure')).toBeInTheDocument();
    expect(screen.getByText('Webhook Configuration')).toBeInTheDocument();
  });

  it('switches to Deployment History tab', async () => {
    renderComponent();
    const historyTab = screen.getByText('Deployment History');
    fireEvent.click(historyTab);
    await waitFor(() => {
      expect(mockGetTenants).toHaveBeenCalled();
    });
  });

  it('shows auto-refresh checkbox on Pipeline Traces tab', async () => {
    renderComponent();
    expect(await screen.findByText('Auto-refresh (5s)')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    renderComponent();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });
});
