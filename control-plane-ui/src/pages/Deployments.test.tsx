import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { createAuthMock, mockDeployment } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// Mock AuthContext
vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
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
const mockListDeployments = vi.fn().mockResolvedValue({
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
});

vi.mock('../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    getTraces: (...args: unknown[]) => mockGetTraces(...args),
    getTraceStats: (...args: unknown[]) => mockGetTraceStats(...args),
    getTrace: vi.fn().mockResolvedValue(null),
    getTenants: (...args: unknown[]) => mockGetTenants(...args),
    getApis: (...args: unknown[]) => mockGetApis(...args),
    listDeployments: (...args: unknown[]) => mockListDeployments(...args),
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
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetTraces.mockResolvedValue({ traces: [] });
    mockGetTraceStats.mockResolvedValue({
      total: 42,
      success_rate: 95.2,
      avg_duration_ms: 1250,
      by_status: { success: 40, failed: 2, pending: 0, in_progress: 0, skipped: 0 },
    });
    mockListDeployments.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
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

  // 4-persona coverage for page render
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(screen.getByRole('heading', { name: 'Deployments' })).toBeInTheDocument();
      });
    }
  );
});

describe('DeploymentHistoryTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetTraces.mockResolvedValue({ traces: [] });
    mockGetTraceStats.mockResolvedValue({
      total: 0,
      success_rate: 0,
      avg_duration_ms: 0,
      by_status: {},
    });
    mockListDeployments.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  async function switchToHistoryTab() {
    renderComponent();
    fireEvent.click(screen.getByText('Deployment History'));
    await waitFor(() => {
      expect(mockGetTenants).toHaveBeenCalled();
    });
  }

  it('calls listDeployments with tenant id', async () => {
    await switchToHistoryTab();
    await waitFor(() => {
      expect(mockListDeployments).toHaveBeenCalledWith('oasis-gunters', {
        api_id: undefined,
        environment: undefined,
        status: undefined,
        page: 1,
        page_size: 20,
      });
    });
  });

  it('shows empty state when no deployments', async () => {
    await switchToHistoryTab();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('renders deployment rows with API name and environment badge', async () => {
    mockListDeployments.mockResolvedValue({
      items: [
        mockDeployment({ api_name: 'Customer API', environment: 'production', status: 'success' }),
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await switchToHistoryTab();
    await waitFor(() => {
      expect(screen.getByText('Customer API')).toBeInTheDocument();
    });
    expect(screen.getByText('PRODUCTION')).toBeInTheDocument();
  });

  it('shows rollback info for rollback deployments', async () => {
    mockListDeployments.mockResolvedValue({
      items: [
        mockDeployment({
          status: 'success',
          rollback_of: 'deploy-old',
          rollback_version: '0.9.0',
        }),
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await switchToHistoryTab();
    await waitFor(() => {
      expect(screen.getByText(/rollback → v0.9.0/)).toBeInTheDocument();
    });
  });

  it('shows error message for failed deployments', async () => {
    mockListDeployments.mockResolvedValue({
      items: [
        mockDeployment({
          status: 'failed',
          error_message: 'Gateway timeout during sync',
        }),
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await switchToHistoryTab();
    await waitFor(() => {
      expect(screen.getByText('Gateway timeout during sync')).toBeInTheDocument();
    });
  });

  it('renders pagination when multiple pages', async () => {
    mockListDeployments.mockResolvedValue({
      items: Array.from({ length: 20 }, (_, i) =>
        mockDeployment({ id: `deploy-${i}`, api_name: `API ${i}` })
      ),
      total: 45,
      page: 1,
      page_size: 20,
    });
    await switchToHistoryTab();
    await waitFor(() => {
      expect(screen.getByText('1 / 3')).toBeInTheDocument();
    });
    expect(screen.getByText('Previous')).toBeInTheDocument();
    expect(screen.getByText('Next')).toBeInTheDocument();
  });

  // 4-persona RBAC: rollback button visibility
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona — rollback button',
    (role) => {
      it(`${['cpi-admin', 'tenant-admin', 'devops'].includes(role) ? 'shows' : 'hides'} rollback button`, async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        mockListDeployments.mockResolvedValue({
          items: [mockDeployment({ status: 'success' })],
          total: 1,
          page: 1,
          page_size: 20,
        });
        await switchToHistoryTab();
        await waitFor(() => {
          expect(screen.getByText('Payment API')).toBeInTheDocument();
        });
        if (['cpi-admin', 'tenant-admin', 'devops'].includes(role)) {
          expect(screen.getByText('Rollback')).toBeInTheDocument();
        } else {
          expect(screen.queryByText('Rollback')).not.toBeInTheDocument();
        }
      });
    }
  );

  it('does not show rollback for non-success deployments', async () => {
    mockListDeployments.mockResolvedValue({
      items: [mockDeployment({ status: 'failed' })],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await switchToHistoryTab();
    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });
    expect(screen.queryByText('Rollback')).not.toBeInTheDocument();
  });

  it('renders filter dropdowns', async () => {
    await switchToHistoryTab();
    await waitFor(() => {
      expect(screen.getByText('Tenant')).toBeInTheDocument();
    });
    expect(screen.getByText('API')).toBeInTheDocument();
    expect(screen.getByText('Environment')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
  });
});
