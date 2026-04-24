import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockApiGet = vi.fn();

vi.mock('../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockApiGet(...args),
  },
}));

vi.mock('../config', () => ({
  config: {
    services: {
      grafana: { url: '/grafana/' },
    },
  },
}));

vi.mock('../utils/navigation', () => ({
  observabilityPath: (url: string) => url,
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

import { APIMonitoring } from './APIMonitoring';

function renderAPIMonitoring() {
  return render(
    <MemoryRouter>
      <APIMonitoring />
    </MemoryRouter>
  );
}

describe('APIMonitoring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockApiGet.mockRejectedValue(new Error('API unavailable'));
  });

  it('renders the page heading', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('API Monitoring')).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText(/Real-time E2E transaction tracing/)).toBeInTheDocument();
  });

  it('renders the search input placeholder', async () => {
    renderAPIMonitoring();
    expect(
      await screen.findByPlaceholderText('Search by trace ID, API, or path...')
    ).toBeInTheDocument();
  });

  it('renders the auto-refresh toggle button (Live by default)', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Live')).toBeInTheDocument();
  });

  it('renders the Refresh button', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('renders error banner when API calls fail', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Transaction monitoring is unavailable')).toBeInTheDocument();
  });

  it('P1-1: transactions still render when /stats fails (allSettled, no clobber)', async () => {
    // Regression: prior Promise.all + catch path wiped transactions to []
    // whenever any sibling endpoint failed, hiding valid data from the user.
    const transactions = [
      {
        id: 't-1',
        trace_id: 'trace-1',
        api_name: 'Payment API',
        method: 'POST',
        path: '/pay',
        status_code: 200,
        status: 'success',
        status_text: 'OK',
        error_source: null,
        started_at: new Date().toISOString(),
        total_duration_ms: 42,
        spans_count: 3,
      },
    ];
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/stats')) {
        return Promise.reject(new Error('Stats endpoint 500'));
      }
      return Promise.resolve({ data: { transactions, demo_mode: false } });
    });
    renderAPIMonitoring();

    // Assert via the trace_id in the row (unique) — Payment API itself
    // appears twice (filter dropdown + row), but trace_id-derived UI only
    // appears when the fulfilled transactions slice rendered.
    expect(await screen.findByText(/trace-1/)).toBeInTheDocument();
    // No global error banner — the dashboard is only partially degraded,
    // not wholly unavailable.
    expect(
      screen.queryByText('Transaction monitoring is unavailable'),
    ).not.toBeInTheDocument();
  });

  it('renders stats cards when API data loads successfully', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/stats')) {
        return Promise.resolve({
          data: {
            total_requests: 1234,
            success_count: 1220,
            error_count: 3,
            timeout_count: 0,
            avg_latency_ms: 42,
            p95_latency_ms: 120,
            p99_latency_ms: 200,
            requests_per_minute: 10,
            by_api: {},
            by_status_code: {},
          },
        });
      }
      // transactions endpoint
      return Promise.resolve({ data: { transactions: [], demo_mode: false } });
    });
    renderAPIMonitoring();
    expect(await screen.findByText('Total Requests')).toBeInTheDocument();
    expect(screen.getByText('Success Rate')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    expect(screen.getByText('APDEX')).toBeInTheDocument();
    expect(screen.getByText('Errors')).toBeInTheDocument();
  });

  it('renders transaction table column headers', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Trace ID')).toBeInTheDocument();
    expect(screen.getByText('Method')).toBeInTheDocument();
    expect(screen.getByText('API / Path')).toBeInTheDocument();
    expect(screen.getByText('Duration')).toBeInTheDocument();
  });

  it('renders the Open in Grafana button', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Open in Grafana')).toBeInTheDocument();
  });

  it('renders waterfall rows when transaction detail expands with spans', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/stats')) {
        return Promise.resolve({
          data: {
            total_requests: 10,
            success_count: 10,
            error_count: 0,
            timeout_count: 0,
            avg_latency_ms: 50,
            p95_latency_ms: 100,
            p99_latency_ms: 200,
            requests_per_minute: 1,
            by_api: {},
            by_status_code: {},
          },
        });
      }
      if (url.includes('/transactions/txn-1')) {
        return Promise.resolve({
          data: {
            id: 'txn-1',
            trace_id: 'trace-abc',
            api_name: 'apis',
            tenant_id: 'tenant-1',
            method: 'GET',
            path: '/v1/apis',
            status_code: 200,
            status: 'success',
            started_at: '2026-03-13T10:00:00Z',
            total_duration_ms: 50,
            spans: [
              {
                name: 'identity',
                service: 'gateway-identity',
                status: 'success',
                start_offset_ms: 0,
                duration_ms: 2,
              },
              {
                name: 'auth',
                service: 'gateway-auth',
                status: 'success',
                start_offset_ms: 2,
                duration_ms: 5,
              },
              {
                name: 'backend_call',
                service: 'gateway-backend',
                status: 'success',
                start_offset_ms: 7,
                duration_ms: 40,
              },
            ],
          },
        });
      }
      // transactions list
      return Promise.resolve({
        data: {
          transactions: [
            {
              id: 'txn-1',
              trace_id: 'trace-abc',
              api_name: 'apis',
              method: 'GET',
              path: '/v1/apis',
              status_code: 200,
              status: 'success',
              started_at: '2026-03-13T10:00:00Z',
              total_duration_ms: 50,
              spans_count: 3,
            },
          ],
          demo_mode: false,
        },
      });
    });

    renderAPIMonitoring();

    // Wait for transaction row to appear — trace_id is displayed
    const traceCell = await screen.findByText(/trace-ab/);
    // Click the row to expand it
    fireEvent.click(traceCell);

    // Waterfall should render 3 span rows
    const waterfallRows = await screen.findAllByTestId('waterfall-row');
    expect(waterfallRows).toHaveLength(3);

    // Check span labels rendered in waterfall
    expect(screen.getByText('identity')).toBeInTheDocument();
    expect(screen.getByText('auth')).toBeInTheDocument();
    expect(screen.getByText('backend_call')).toBeInTheDocument();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderAPIMonitoring();
        expect(await screen.findByText('API Monitoring')).toBeInTheDocument();
      });
    }
  );
});
