import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TraceDetail } from './TraceDetail';

// Mock apiService to reject (triggers demo data fallback)
vi.mock('../../services/api', () => ({
  apiService: {
    getTransactionDetail: vi.fn().mockRejectedValue(new Error('mock')),
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

describe('TraceDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
