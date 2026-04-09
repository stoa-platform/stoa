/**
 * Regression: CAB-2034 — Call-Flow must NOT generate demo data
 *
 * Before this fix, when the monitoring API returned 0 transactions or failed,
 * the UI generated fake traces (routes /customers, /orders, tenant-acme)
 * which masked a broken observability pipeline in production for 3+ weeks.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock apiService BEFORE importing TraceDetail (same pattern as TraceDetail.test.tsx)
vi.mock('../../services/api', () => ({
  apiService: {
    getTransactionDetail: vi.fn().mockRejectedValue(new Error('API unavailable')),
  },
}));

// Import AFTER mock declaration (vitest hoists vi.mock but this makes intent clear)
import { TraceDetail } from '../../pages/CallFlow/TraceDetail';

function renderTraceDetail(traceId: string) {
  return render(
    <MemoryRouter initialEntries={[`/call-flow/trace/${traceId}`]}>
      <Routes>
        <Route path="/call-flow/trace/:traceId" element={<TraceDetail />} />
        <Route path="/call-flow" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('regression/CAB-2034', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows "Trace not found" instead of demo data when API fails', async () => {
    renderTraceDetail('test-trace-001');
    await waitFor(() => {
      expect(screen.getByText('Trace not found')).toBeInTheDocument();
    });
    // Must NOT contain any demo data markers
    expect(screen.queryByText('customer-api')).not.toBeInTheDocument();
    expect(screen.queryByText('tenant-acme')).not.toBeInTheDocument();
    expect(screen.queryByText('Demo data')).not.toBeInTheDocument();
  });
});
