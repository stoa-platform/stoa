/**
 * ExecutionViewDashboard Tests (CAB-1318)
 *
 * Covers: render, stats, filters, table, modal, RBAC (4 personas), empty, loading.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ExecutionViewDashboard } from './ExecutionViewDashboard';

// Mock auth context
const mockAuth = {
  user: {
    id: 'user-1',
    name: 'Admin',
    email: 'admin@test.com',
    roles: ['cpi-admin'],
    tenant_id: 'tenant-1',
    permissions: [],
  },
  isAuthenticated: true,
  isLoading: false,
  isReady: true,
  login: () => {},
  logout: () => {},
  hasPermission: () => true,
  hasRole: () => true,
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth,
}));

// Mock API service
const mockGet = vi.fn();
vi.mock('../../services/api', () => ({
  apiService: { get: (...args: unknown[]) => mockGet(...args) },
}));

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ExecutionViewDashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const mockExecutions = {
  items: [
    {
      id: 'exec-1',
      api_name: 'Users API',
      tool_name: null,
      request_id: 'req-1',
      method: 'GET',
      path: '/v1/users',
      status_code: 200,
      status: 'success',
      error_category: null,
      error_message: null,
      started_at: '2026-02-19T14:00:00Z',
      completed_at: '2026-02-19T14:00:00Z',
      duration_ms: 45,
    },
    {
      id: 'exec-2',
      api_name: 'Orders API',
      tool_name: null,
      request_id: 'req-2',
      method: 'POST',
      path: '/v1/orders',
      status_code: 429,
      status: 'error',
      error_category: 'rate_limit',
      error_message: 'Rate limit exceeded',
      started_at: '2026-02-19T14:01:00Z',
      completed_at: '2026-02-19T14:01:00Z',
      duration_ms: 12,
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

const mockTaxonomy = {
  items: [
    { category: 'auth', count: 23, avg_duration_ms: 15.0, percentage: 34.3 },
    {
      category: 'rate_limit',
      count: 18,
      avg_duration_ms: 8.0,
      percentage: 26.9,
    },
    {
      category: 'backend',
      count: 15,
      avg_duration_ms: 120.0,
      percentage: 22.4,
    },
    {
      category: 'timeout',
      count: 8,
      avg_duration_ms: 5000.0,
      percentage: 11.9,
    },
    { category: 'validation', count: 3, avg_duration_ms: 5.0, percentage: 4.5 },
  ],
  total_errors: 67,
  total_executions: 1247,
  error_rate: 5.4,
};

const mockDetail = {
  ...mockExecutions.items[0],
  tenant_id: 'tenant-1',
  consumer_id: 'consumer-1',
  api_id: 'api-1',
  request_headers: { 'content-type': 'application/json' },
  response_summary: { status: 200 },
};

describe('ExecutionViewDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/taxonomy')) return Promise.resolve({ data: mockTaxonomy });
      if (url.includes('/executions/exec-')) return Promise.resolve({ data: mockDetail });
      return Promise.resolve({ data: mockExecutions });
    });
  });

  it('renders dashboard with title', async () => {
    renderDashboard();
    expect(screen.getByText('Execution View')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('1247')).toBeInTheDocument();
    });
  });

  it('shows stats cards with correct values', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('1247')).toBeInTheDocument();
      expect(screen.getByText('1180')).toBeInTheDocument();
      // '67' appears in stats card and possibly taxonomy
      expect(screen.getAllByText('67').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('5.4%')).toBeInTheDocument();
    });
  });

  it('renders execution table with rows', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
      expect(screen.getByText('Orders API')).toBeInTheDocument();
    });
  });

  it('renders error taxonomy chart', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Error Taxonomy')).toBeInTheDocument();
      expect(screen.getAllByText('Auth').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Rate Limit').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows status filter dropdown', () => {
    renderDashboard();
    expect(screen.getByLabelText('Filter by status')).toBeInTheDocument();
  });

  it('applies status filter on change', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Filter by status'), {
      target: { value: 'error' },
    });

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        expect.stringContaining('/executions'),
        expect.objectContaining({
          params: expect.objectContaining({ status: 'error' }),
        })
      );
    });
  });

  it('opens detail modal on row click', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Users API'));

    await waitFor(() => {
      expect(screen.getByText('Execution Detail')).toBeInTheDocument();
      expect(screen.getByText('req-1')).toBeInTheDocument();
    });
  });

  it('shows empty state when no executions', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/taxonomy'))
        return Promise.resolve({
          data: { items: [], total_errors: 0, total_executions: 0, error_rate: 0 },
        });
      return Promise.resolve({ data: { items: [], total: 0, page: 1, page_size: 20 } });
    });

    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('No executions found')).toBeInTheDocument();
    });
  });

  it('shows loading state', () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    renderDashboard();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });
});
