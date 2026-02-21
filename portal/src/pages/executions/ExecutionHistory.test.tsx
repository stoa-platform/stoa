/**
 * ExecutionHistory Tests (CAB-1318)
 *
 * Covers: render, stats, table, filter, empty, loading, error breakdown.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ExecutionHistoryPage } from './ExecutionHistory';

// Mock auth
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    accessToken: 'test-token',
    user: { name: 'Dev', email: 'dev@test.com', roles: ['viewer'] },
    hasPermission: () => true,
    hasScope: () => true,
    hasRole: () => true,
  }),
}));

// Mock services
const mockList = vi.fn();
const mockGetTaxonomy = vi.fn();

vi.mock('../../services/executions', () => ({
  executionsService: {
    list: (...args: unknown[]) => mockList(...args),
    getTaxonomy: () => mockGetTaxonomy(),
  },
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ExecutionHistoryPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const mockExecutionsData = {
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

const mockTaxonomyData = {
  items: [
    { category: 'auth', count: 4, avg_duration_ms: 10.0, percentage: 33.3 },
    {
      category: 'rate_limit',
      count: 5,
      avg_duration_ms: 8.0,
      percentage: 41.7,
    },
    { category: 'backend', count: 3, avg_duration_ms: 120.0, percentage: 25.0 },
  ],
  total_errors: 12,
  total_executions: 234,
  error_rate: 5.1,
};

describe('ExecutionHistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue(mockExecutionsData);
    mockGetTaxonomy.mockResolvedValue(mockTaxonomyData);
  });

  it('renders page title', async () => {
    renderPage();
    expect(screen.getByText('My Execution History')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('234')).toBeInTheDocument();
    });
  });

  it('shows stats cards', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('234')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
    });
  });

  it('shows error breakdown tags', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Auth: 4')).toBeInTheDocument();
      // Rate Limit appears in breakdown AND possibly table
      expect(screen.getAllByText(/Rate Limit/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders execution table', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
      expect(screen.getByText('Orders API')).toBeInTheDocument();
    });
  });

  it('shows status filter', () => {
    renderPage();
    expect(screen.getByLabelText('Filter by status')).toBeInTheDocument();
  });

  it('applies status filter', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Filter by status'), {
      target: { value: 'error' },
    });

    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
    });
  });

  it('shows empty state', async () => {
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockGetTaxonomy.mockResolvedValue({
      items: [],
      total_errors: 0,
      total_executions: 0,
      error_rate: 0,
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText('No executions found')).toBeInTheDocument();
    });
  });

  it('shows loading state', () => {
    mockList.mockImplementation(() => new Promise(() => {}));
    mockGetTaxonomy.mockImplementation(() => new Promise(() => {}));

    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });
});
