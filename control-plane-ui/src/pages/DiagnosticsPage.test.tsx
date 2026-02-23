import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { createAuthMock, type PersonaRole } from '../test/helpers';
import { DiagnosticsPage } from './DiagnosticsPage';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../services/api', () => ({
  apiService: {
    get: vi.fn().mockResolvedValue({ data: [] }),
  },
}));

vi.mock('../services/diagnosticService', () => ({
  runDiagnostic: vi.fn().mockResolvedValue({
    id: 'diag-1',
    timestamp: '2026-02-23T12:00:00Z',
    tenant_id: 't1',
    gateway_id: 'gw1',
    root_causes: [
      {
        category: 'auth',
        confidence: 0.9,
        summary: 'JWT expired',
        evidence: ['401 Unauthorized'],
        suggested_fix: 'Refresh token',
      },
    ],
    timing: { gateway_ms: 5, backend_ms: 120, total_ms: 125 },
    network_path: null,
    redacted: true,
  }),
  checkConnectivity: vi.fn().mockResolvedValue({
    overall_status: 'healthy',
    stages: [
      { name: 'dns', status: 'ok', latency_ms: 2, detail: null },
      { name: 'tcp', status: 'ok', latency_ms: 5, detail: null },
      { name: 'tls', status: 'ok', latency_ms: 15, detail: null },
      { name: 'http', status: 'ok', latency_ms: 25, detail: null },
    ],
    network_path: null,
    checked_at: '2026-02-23T12:00:00Z',
  }),
  getDiagnosticHistory: vi.fn().mockResolvedValue([]),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DiagnosticsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('DiagnosticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders gateway selector', () => {
    renderPage();
    expect(screen.getByText('Select Gateway')).toBeInTheDocument();
  });

  it('renders page heading', () => {
    renderPage();
    expect(screen.getByText('Platform Diagnostics')).toBeInTheDocument();
  });

  it('renders connectivity test section', () => {
    renderPage();
    expect(screen.getByText('Connectivity Test')).toBeInTheDocument();
  });

  it('shows run diagnostic button', () => {
    renderPage();
    expect(screen.getByText('Run Diagnostic')).toBeInTheDocument();
  });

  it('shows check connectivity button', () => {
    renderPage();
    expect(screen.getByText('Check Connectivity')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderPage();
        await waitFor(() => {
          expect(screen.getByText('Platform Diagnostics')).toBeInTheDocument();
        });
      });
    }
  );
});
