import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { createAuthMock, mockExternalMCPServer } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockServer = {
  ...mockExternalMCPServer(),
  tools: [
    {
      id: 'tool-1',
      name: 'list-issues',
      namespaced_name: 'linear/list-issues',
      description: 'List Linear issues',
      enabled: true,
      synced_at: '2026-02-01T00:00:00Z',
    },
  ],
};

const mockGetServer = vi.fn().mockResolvedValue(mockServer);

vi.mock('../../services/externalMcpServersApi', () => ({
  externalMcpServersService: {
    getServer: (...args: unknown[]) => mockGetServer(...args),
    updateServer: vi.fn().mockResolvedValue({}),
    testConnection: vi.fn().mockResolvedValue({ success: true, latency_ms: 100 }),
    syncTools: vi.fn().mockResolvedValue({ synced_count: 5, removed_count: 0, tools: [] }),
    updateTool: vi.fn().mockResolvedValue({}),
    deleteServer: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('./ExternalMCPServerModal', () => ({
  ExternalMCPServerModal: () => <div data-testid="edit-modal">Edit Modal</div>,
}));

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

import { ExternalMCPServerDetail } from './ExternalMCPServerDetail';

function renderServerDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/servers/srv-1']}>
        <Routes>
          <Route path="/servers/:id" element={<ExternalMCPServerDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ExternalMCPServerDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetServer.mockResolvedValue(mockServer);
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the server display name', async () => {
    renderServerDetail();
    expect(await screen.findByText('Linear')).toBeInTheDocument();
  });

  it('renders the server base URL', async () => {
    renderServerDetail();
    expect(await screen.findByText('https://mcp.linear.app')).toBeInTheDocument();
  });

  it('renders health status badge', async () => {
    renderServerDetail();
    expect(await screen.findByText(/Healthy/i)).toBeInTheDocument();
  });

  it('renders action buttons', async () => {
    renderServerDetail();
    expect(await screen.findByText(/Test Connection/i)).toBeInTheDocument();
    expect(screen.getByText(/Sync Tools/i)).toBeInTheDocument();
  });

  it('renders tools list', async () => {
    renderServerDetail();
    expect(await screen.findByText('list-issues')).toBeInTheDocument();
  });

  it('renders delete server button in danger zone', async () => {
    renderServerDetail();
    expect(await screen.findByText(/Delete Server/i)).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    mockGetServer.mockReturnValue(new Promise(() => {}));
    renderServerDetail();
    expect(screen.getAllByTestId('card-skeleton').length).toBeGreaterThanOrEqual(1);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderServerDetail();
        expect(await screen.findByText('Linear')).toBeInTheDocument();
      });
    }
  );
});
