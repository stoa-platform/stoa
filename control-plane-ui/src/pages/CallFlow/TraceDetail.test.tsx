import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TraceDetail } from './TraceDetail';

// Mock apiService — first test group rejects, second resolves
const mockGetTransactionDetail = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    getTransactionDetail: (...args: unknown[]) => mockGetTransactionDetail(...args),
  },
}));

function renderWithRoute(traceId: string) {
  return render(
    <MemoryRouter initialEntries={[`/call-flow/trace/${traceId}`]}>
      <Routes>
        <Route path="/call-flow/trace/:traceId" element={<TraceDetail />} />
        <Route path="/call-flow" element={<div>Dashboard</div>} />
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
      metadata: {},
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
          expect(screen.getByText('Back to Call Flow')).toBeInTheDocument();
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
  });

  describe('when API fails', () => {
    beforeEach(() => {
      mockGetTransactionDetail.mockRejectedValue(new Error('network error'));
    });

    it('shows trace not found', async () => {
      renderWithRoute('test-trace-001');
      await waitFor(() => {
        expect(screen.getByText('Trace not found')).toBeInTheDocument();
      });
    });
  });
});
