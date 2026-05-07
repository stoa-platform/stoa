import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { TraceDetail } from './TraceDetail';

const mockGetTransactionDetail = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    getTransactionDetail: (...args: unknown[]) => mockGetTransactionDetail(...args),
  },
}));

function LogsProbe() {
  const location = useLocation();
  return <div data-testid="logs-search">{location.search}</div>;
}

function renderWithRoute(traceId: string) {
  return render(
    <MemoryRouter initialEntries={[`/observability/live-calls/trace/${traceId}`]}>
      <Routes>
        <Route path="/observability/live-calls/trace/:traceId" element={<TraceDetail />} />
        <Route path="/observability/live-calls" element={<div>Live Calls</div>} />
        <Route path="/logs" element={<LogsProbe />} />
        <Route path="/call-flow/trace/:traceId" element={<TraceDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

const MOCK_DETAIL = {
  id: 'test-trace-001',
  trace_id: 'trace-test0001',
  api_name: 'exchange-rate-api',
  tenant_id: 'demo',
  method: 'GET',
  path: '/v4/latest/EUR',
  status_code: 200,
  status: 'success',
  status_text: 'OK',
  error_source: null,
  client_ip: '10.0.1.42',
  user_id: 'user-test',
  started_at: new Date().toISOString(),
  total_duration_ms: 45,
  spans: [
    {
      name: 'gateway_ingress',
      service: 'stoa-gateway',
      start_offset_ms: 0,
      duration_ms: 5,
      status: 'success',
      metadata: { span_id: 'span-test0001' },
    },
    {
      name: 'auth_validation',
      service: 'keycloak',
      start_offset_ms: 5,
      duration_ms: 15,
      status: 'success',
      metadata: {},
    },
    {
      name: 'backend_call',
      service: 'upstream-api',
      start_offset_ms: 20,
      duration_ms: 25,
      status: 'success',
      metadata: {},
    },
  ],
  request_headers: {
    'Content-Type': 'application/json',
    Authorization: 'Bearer eyJ...real',
    'X-STOA-Tenant': 'demo',
  },
  response_headers: {
    'Content-Type': 'application/json',
    'X-STOA-Duration-Ms': '45',
    'X-STOA-Version': '0.9.23',
  },
  error_message: null,
};

describe('TraceDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('when API returns data', () => {
    beforeEach(() => {
      mockGetTransactionDetail.mockResolvedValue(MOCK_DETAIL);
    });

    it('renders trace detail after loading', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(
        () => {
          expect(screen.getByText('Back to Live Calls')).toBeInTheDocument();
        },
        { timeout: 3000 }
      );
      expect(screen.getByText('Trace Waterfall')).toBeInTheDocument();
      expect(screen.getByText('Middleware Pipeline')).toBeInTheDocument();
      expect(screen.getByText(/Gateway Metrics/)).toBeInTheDocument();
    });

    it('renders request/response header tabs', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(
        () => {
          expect(screen.getByText(/request headers/i)).toBeInTheDocument();
        },
        { timeout: 3000 }
      );
      expect(screen.getByText(/response headers/i)).toBeInTheDocument();
    });

    it('redacts sensitive headers', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(
        () => {
          expect(screen.getByText(/request headers/i)).toBeInTheDocument();
        },
        { timeout: 3000 }
      );
      const redacted = screen.queryAllByText(/••••••••/);
      expect(redacted.length).toBeGreaterThan(0);
    });

    it('renders summary cards', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(() => {
        expect(screen.getByText('Status')).toBeInTheDocument();
      });
      expect(screen.getByText('Duration')).toBeInTheDocument();
      expect(screen.getByText('Gateway')).toBeInTheDocument();
      expect(screen.getByText('Auth')).toBeInTheDocument();
      expect(screen.getByText('Upstream')).toBeInTheDocument();
      expect(screen.getByText('Retries')).toBeInTheDocument();
    });

    it('surfaces canonical trace context fields', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(() => {
        expect(screen.getByText('Trace Context')).toBeInTheDocument();
      });

      expect(screen.getByText('trace_id')).toBeInTheDocument();
      expect(screen.getAllByText('trace-test0001').length).toBeGreaterThan(0);
      expect(screen.getByText('span_id')).toBeInTheDocument();
      expect(screen.getByText('span-test0001')).toBeInTheDocument();
      expect(screen.getByText('tenant_id')).toBeInTheDocument();
      expect(screen.getByText('service.name')).toBeInTheDocument();
      expect(screen.getByText('service.version')).toBeInTheDocument();
      expect(screen.getByText('0.9.23')).toBeInTheDocument();
      expect(screen.getByText('http_route')).toBeInTheDocument();
      expect(screen.getByText('status_class')).toBeInTheDocument();
      expect(screen.getByText('2xx')).toBeInTheDocument();
    });

    it('links to the existing logs route with trace search parameters', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(() => {
        expect(screen.getByText('Trace Context')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /view logs for trace/i }));

      await waitFor(() => {
        expect(screen.getByTestId('logs-search')).toHaveTextContent(
          '?service=gateway&trace_id=trace-test0001'
        );
      });
    });
  });

  describe('when API fails', () => {
    beforeEach(() => {
      mockGetTransactionDetail.mockRejectedValue(new Error('network error'));
    });

    it('shows trace not found with guidance', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(() => {
        expect(screen.getByText(/trace not found/i)).toBeInTheDocument();
      });
      expect(screen.getByRole('button', { name: /back to live calls/i })).toBeInTheDocument();
    });
  });
});
