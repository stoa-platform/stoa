import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { createAuthMock, type PersonaRole } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';

// Mock hooks
const mockRefetch = vi.fn();
const mockMutateAsync = vi.fn();
vi.mock('../hooks/usePlatformStatus', () => ({
  usePlatformStatus: vi.fn(),
  useSyncComponent: vi.fn(),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  MemoryRouter: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('../utils/navigation', () => ({
  observabilityPath: (url?: string) =>
    `/observability${url ? `?url=${encodeURIComponent(url)}` : ''}`,
  logsPath: (url?: string) => `/logs${url ? `?url=${encodeURIComponent(url)}` : ''}`,
}));

import { usePlatformStatus, useSyncComponent } from '../hooks/usePlatformStatus';
import { PlatformStatus } from './PlatformStatus';

const mockUsePlatformStatus = vi.mocked(usePlatformStatus);
const mockUseSyncComponent = vi.mocked(useSyncComponent);

function renderComponent(props: { compact?: boolean; onStatusChange?: (s: string) => void } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { container } = render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(PlatformStatus, props)
    )
  );
  return container;
}

const mockStatus = {
  gitops: {
    status: 'healthy',
    components: [
      {
        name: 'stoa-gateway',
        display_name: 'STOA Gateway',
        sync_status: 'Synced',
        health_status: 'Healthy',
        revision: 'abc1234567890',
        last_sync: new Date().toISOString(),
      },
      {
        name: 'control-plane-api',
        display_name: 'Control Plane API',
        sync_status: 'OutOfSync',
        health_status: 'Degraded',
        revision: 'def4567890123',
        last_sync: new Date().toISOString(),
      },
    ],
  },
  events: [],
  external_links: {
    argocd: 'https://argocd.test',
    grafana: 'https://grafana.test',
    prometheus: 'https://prometheus.test',
    logs: 'https://logs.test',
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  mockUseSyncComponent.mockReturnValue({
    mutateAsync: mockMutateAsync,
    isPending: false,
  } as any);
});

describe('PlatformStatus', () => {
  it('renders loading state', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('Loading platform status...')).toBeInTheDocument();
  });

  it('renders error state with retry button', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Failed'),
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('Status monitoring unavailable')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('returns null when no status and no error/loading', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    const container = renderComponent();
    expect(container.innerHTML).toBe('');
  });

  it('renders full status with components', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: mockStatus,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('Platform Status')).toBeInTheDocument();
    expect(screen.getByText('All Systems Operational')).toBeInTheDocument();
    expect(screen.getByText('STOA Gateway')).toBeInTheDocument();
    expect(screen.getByText('Control Plane API')).toBeInTheDocument();
  });

  it('renders compact mode', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: mockStatus,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent({ compact: true });
    expect(screen.getByText('All Systems Operational')).toBeInTheDocument();
    // compact mode should not show component cards
    expect(screen.queryByText('STOA Gateway')).not.toBeInTheDocument();
  });

  it('shows sync button for OutOfSync components', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: mockStatus,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('Sync Now')).toBeInTheDocument();
  });

  it('renders external links', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: mockStatus,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('ArgoCD')).toBeInTheDocument();
    expect(screen.getByText('Grafana')).toBeInTheDocument();
    expect(screen.getByText('Prometheus')).toBeInTheDocument();
    expect(screen.getByText('Logs')).toBeInTheDocument();
  });

  it('shows revision short hash', () => {
    mockUsePlatformStatus.mockReturnValue({
      data: mockStatus,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('abc1234')).toBeInTheDocument();
  });

  it('renders degraded status config', () => {
    const degradedStatus = {
      ...mockStatus,
      gitops: { ...mockStatus.gitops, status: 'degraded' },
    };
    mockUsePlatformStatus.mockReturnValue({
      data: degradedStatus,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('System Degraded')).toBeInTheDocument();
  });

  it('renders unknown status config', () => {
    const unknownStatus = {
      ...mockStatus,
      gitops: { ...mockStatus.gitops, status: 'other' },
    };
    mockUsePlatformStatus.mockReturnValue({
      data: unknownStatus,
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as any);

    renderComponent();
    expect(screen.getByText('Checking Status...')).toBeInTheDocument();
  });

  // CAB-1553: 4-persona RBAC tests for dashboard widgets
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        mockUsePlatformStatus.mockReturnValue({
          data: mockStatus,
          isLoading: false,
          error: null,
          refetch: mockRefetch,
        } as any);
      });

      it('sees platform status heading and components', () => {
        renderComponent();
        expect(screen.getByText('Platform Status')).toBeInTheDocument();
        expect(screen.getByText('STOA Gateway')).toBeInTheDocument();
        expect(screen.getByText('Control Plane API')).toBeInTheDocument();
      });

      if (role === 'viewer') {
        it('does not see Sync Now button', () => {
          renderComponent();
          expect(screen.queryByText('Sync Now')).not.toBeInTheDocument();
        });

        it('does not see external links', () => {
          renderComponent();
          expect(screen.queryByText('ArgoCD')).not.toBeInTheDocument();
          expect(screen.queryByText('Grafana')).not.toBeInTheDocument();
        });
      } else {
        it('sees Sync Now button for OutOfSync components', () => {
          renderComponent();
          expect(screen.getByText('Sync Now')).toBeInTheDocument();
        });

        it('sees external links', () => {
          renderComponent();
          expect(screen.getByText('ArgoCD')).toBeInTheDocument();
          expect(screen.getByText('Grafana')).toBeInTheDocument();
          expect(screen.getByText('Prometheus')).toBeInTheDocument();
          expect(screen.getByText('Logs')).toBeInTheDocument();
        });
      }
    }
  );
});
