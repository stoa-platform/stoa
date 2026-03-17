import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TraceDetail } from './TraceDetail';

// Mock fetch to return demo data
beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('mock'));
});

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
  it('renders loading state initially', () => {
    renderWithRoute('test-trace-001');
    // Skeleton cards should be visible during loading
    expect(document.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0);
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
    expect(screen.getByText(/Kernel Metrics/)).toBeInTheDocument();
  });

  it('renders request/response header tabs', async () => {
    renderWithRoute('test-trace-001');
    await waitFor(() => {
      expect(screen.getByText('Request Headers')).toBeInTheDocument();
    });
    expect(screen.getByText('Response Headers')).toBeInTheDocument();
  });

  it('redacts sensitive headers', async () => {
    renderWithRoute('test-trace-001');
    await waitFor(() => {
      expect(screen.getByText('Request Headers')).toBeInTheDocument();
    });
    // Authorization header should be redacted
    const redacted = screen.queryAllByText('••••••••');
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
