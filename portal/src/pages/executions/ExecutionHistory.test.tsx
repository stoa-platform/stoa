/**
 * ExecutionHistory Tests (CAB-1318, CAB-1554)
 *
 * Covers: render, stats, taxonomy, table, filters (status, error type,
 * API name, date range), clear, empty, loading — across 4 personas.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { ExecutionHistoryPage } from './ExecutionHistory';
import { createAuthMock, renderWithProviders, type PersonaRole } from '../../test/helpers';

// Mock auth — vi.hoisted ensures mock fn exists before vi.mock runs
const mockAuth = vi.hoisted(() => vi.fn());
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
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

// ============ Mock Data ============

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
    {
      id: 'exec-3',
      api_name: 'Payments API',
      tool_name: null,
      request_id: 'req-3',
      method: 'POST',
      path: '/v1/payments',
      status_code: 502,
      status: 'error',
      error_category: 'upstream',
      error_message: 'Bad gateway',
      started_at: '2026-02-19T14:02:00Z',
      completed_at: '2026-02-19T14:02:00Z',
      duration_ms: 1200,
    },
    {
      id: 'exec-4',
      api_name: 'Auth API',
      tool_name: null,
      request_id: 'req-4',
      method: 'GET',
      path: '/v1/auth/verify',
      status_code: 500,
      status: 'error',
      error_category: 'internal',
      error_message: 'Internal error',
      started_at: '2026-02-19T14:03:00Z',
      completed_at: '2026-02-19T14:03:00Z',
      duration_ms: 80,
    },
  ],
  total: 4,
  page: 1,
  page_size: 20,
};

const mockTaxonomyData = {
  items: [
    { category: 'auth', count: 4, avg_duration_ms: 10.0, percentage: 20.0 },
    { category: 'rate_limit', count: 5, avg_duration_ms: 8.0, percentage: 25.0 },
    { category: 'upstream', count: 3, avg_duration_ms: 120.0, percentage: 15.0 },
    { category: 'validation', count: 2, avg_duration_ms: 5.0, percentage: 10.0 },
    { category: 'internal', count: 4, avg_duration_ms: 90.0, percentage: 20.0 },
    { category: 'timeout', count: 2, avg_duration_ms: 3000.0, percentage: 10.0 },
  ],
  total_errors: 20,
  total_executions: 487,
  error_rate: 4.1,
};

// ============ 4-Persona Tests ============

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'ExecutionHistoryPage — %s persona',
  (role) => {
    beforeEach(() => {
      vi.clearAllMocks();
      mockAuth.mockReturnValue(createAuthMock(role));
      mockList.mockResolvedValue(mockExecutionsData);
      mockGetTaxonomy.mockResolvedValue(mockTaxonomyData);
    });

    it('renders page title and subtitle', async () => {
      renderWithProviders(<ExecutionHistoryPage />);
      expect(screen.getByText('My Execution History')).toBeInTheDocument();
      expect(screen.getByText('View your API call history and error patterns')).toBeInTheDocument();
      await waitFor(() => {
        expect(screen.getByText('487')).toBeInTheDocument();
      });
    });

    it('shows stats cards with taxonomy data', async () => {
      renderWithProviders(<ExecutionHistoryPage />);
      await waitFor(() => {
        expect(screen.getByText('487')).toBeInTheDocument();
        expect(screen.getByText('20')).toBeInTheDocument();
      });
    });

    it('shows all 6 error taxonomy categories', async () => {
      renderWithProviders(<ExecutionHistoryPage />);
      await waitFor(() => {
        expect(screen.getByText('Auth: 4')).toBeInTheDocument();
        expect(screen.getAllByText(/Rate Limit/).length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('Upstream: 3')).toBeInTheDocument();
        expect(screen.getByText('Validation: 2')).toBeInTheDocument();
        expect(screen.getByText('Internal: 4')).toBeInTheDocument();
        expect(screen.getByText('Timeout: 2')).toBeInTheDocument();
      });
    });

    it('renders execution table with API names', async () => {
      renderWithProviders(<ExecutionHistoryPage />);
      await waitFor(() => {
        expect(screen.getByText('Users API')).toBeInTheDocument();
        expect(screen.getByText('Orders API')).toBeInTheDocument();
        expect(screen.getByText('Payments API')).toBeInTheDocument();
        expect(screen.getByText('Auth API')).toBeInTheDocument();
      });
    });

    it('maps error categories in table rows', async () => {
      renderWithProviders(<ExecutionHistoryPage />);
      await waitFor(() => {
        expect(screen.getByText('Rate Limit')).toBeInTheDocument();
        expect(screen.getByText('Upstream')).toBeInTheDocument();
        expect(screen.getByText('Internal')).toBeInTheDocument();
      });
    });
  }
);

// ============ Filter Tests ============

describe('ExecutionHistoryPage — filters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('viewer'));
    mockList.mockResolvedValue(mockExecutionsData);
    mockGetTaxonomy.mockResolvedValue(mockTaxonomyData);
  });

  it('shows all filter controls', async () => {
    renderWithProviders(<ExecutionHistoryPage />);
    expect(screen.getByLabelText('Filter by status')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter by error type')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter by API name')).toBeInTheDocument();
    expect(screen.getByLabelText('Date from')).toBeInTheDocument();
    expect(screen.getByLabelText('Date to')).toBeInTheDocument();
  });

  it('applies status filter', async () => {
    renderWithProviders(<ExecutionHistoryPage />);
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

  it('applies error category filter', async () => {
    renderWithProviders(<ExecutionHistoryPage />);
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Filter by error type'), {
      target: { value: 'auth' },
    });

    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(expect.objectContaining({ error_category: 'auth' }));
    });
  });

  it('applies API name filter', async () => {
    renderWithProviders(<ExecutionHistoryPage />);
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Filter by API name'), {
      target: { value: 'Orders' },
    });

    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(expect.objectContaining({ api_name: 'Orders' }));
    });
  });

  it('applies date range filter', async () => {
    renderWithProviders(<ExecutionHistoryPage />);
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Date from'), {
      target: { value: '2026-02-01' },
    });
    fireEvent.change(screen.getByLabelText('Date to'), {
      target: { value: '2026-02-28' },
    });

    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-02-01', date_to: '2026-02-28' })
      );
    });
  });

  it('shows clear filters button when filters active', async () => {
    renderWithProviders(<ExecutionHistoryPage />);
    expect(screen.queryByText('Clear filters')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Filter by status'), {
      target: { value: 'error' },
    });

    await waitFor(() => {
      expect(screen.getByText('Clear filters')).toBeInTheDocument();
    });
  });

  it('resets all filters on clear', async () => {
    renderWithProviders(<ExecutionHistoryPage />);
    await waitFor(() => {
      expect(screen.getByText('Users API')).toBeInTheDocument();
    });

    // Set multiple filters
    fireEvent.change(screen.getByLabelText('Filter by status'), {
      target: { value: 'error' },
    });
    fireEvent.change(screen.getByLabelText('Filter by error type'), {
      target: { value: 'auth' },
    });

    await waitFor(() => {
      expect(screen.getByText('Clear filters')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Clear filters'));

    await waitFor(() => {
      expect(screen.queryByText('Clear filters')).not.toBeInTheDocument();
    });
    expect((screen.getByLabelText('Filter by status') as HTMLSelectElement).value).toBe('');
    expect((screen.getByLabelText('Filter by error type') as HTMLSelectElement).value).toBe('');
  });

  it('error type dropdown has all taxonomy categories', () => {
    renderWithProviders(<ExecutionHistoryPage />);
    const select = screen.getByLabelText('Filter by error type') as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain('');
    expect(options).toContain('auth');
    expect(options).toContain('rate_limit');
    expect(options).toContain('upstream');
    expect(options).toContain('validation');
    expect(options).toContain('internal');
    expect(options).toContain('timeout');
  });
});

// ============ Edge Cases ============

describe('ExecutionHistoryPage — edge cases', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('viewer'));
  });

  it('shows empty state', async () => {
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockGetTaxonomy.mockResolvedValue({
      items: [],
      total_errors: 0,
      total_executions: 0,
      error_rate: 0,
    });

    renderWithProviders(<ExecutionHistoryPage />);
    await waitFor(() => {
      expect(screen.getByText('No executions found')).toBeInTheDocument();
    });
  });

  it('shows loading state', () => {
    mockList.mockImplementation(() => new Promise(() => {}));
    mockGetTaxonomy.mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<ExecutionHistoryPage />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('handles unknown error category gracefully', async () => {
    mockList.mockResolvedValue({
      items: [
        {
          id: 'exec-unk',
          api_name: 'Mystery API',
          tool_name: null,
          request_id: 'req-unk',
          method: 'GET',
          path: '/v1/mystery',
          status_code: 500,
          status: 'error',
          error_category: 'unknown_category',
          error_message: 'Unknown',
          started_at: '2026-02-19T14:00:00Z',
          completed_at: '2026-02-19T14:00:00Z',
          duration_ms: 50,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockGetTaxonomy.mockResolvedValue(mockTaxonomyData);

    renderWithProviders(<ExecutionHistoryPage />);
    await waitFor(() => {
      // Falls back to raw category string when no label match
      expect(screen.getByText('unknown_category')).toBeInTheDocument();
    });
  });

  it('renders all 6 category labels in filter dropdown', () => {
    mockList.mockResolvedValue(mockExecutionsData);
    mockGetTaxonomy.mockResolvedValue(mockTaxonomyData);
    renderWithProviders(<ExecutionHistoryPage />);
    const select = screen.getByLabelText('Filter by error type') as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map((o) => o.text);
    expect(optionLabels).toContain('Auth');
    expect(optionLabels).toContain('Rate Limit');
    expect(optionLabels).toContain('Upstream');
    expect(optionLabels).toContain('Validation');
    expect(optionLabels).toContain('Internal');
    expect(optionLabels).toContain('Timeout');
    // 6 categories + 1 "All Error Types" placeholder
    expect(select.options).toHaveLength(7);
  });
});
