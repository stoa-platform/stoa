import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// Mock AuthContext
vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

// Mock errorSnapshotsService — uses CP API types now
const mockGetSnapshots = vi.fn().mockResolvedValue({
  items: [
    {
      id: 'SNP-20260115-094512-a1b2c3d4',
      timestamp: '2026-01-15T09:45:12.345Z',
      tenant_id: 'oasis-gunters',
      trigger: '5xx',
      status: 502,
      method: 'POST',
      path: '/api/v1/payments',
      duration_ms: 30042,
      source: 'stoa',
      resolution_status: 'unresolved',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
});
const mockGetStats = vi.fn().mockResolvedValue({
  total: 15,
  by_trigger: { '5xx': 8, '4xx': 4, timeout: 3 },
  by_status_code: { 500: 5, 502: 3, 400: 4, 504: 3 },
  resolution_stats: { unresolved: 5, investigating: 3, resolved: 6, ignored: 1 },
  period: { start: null, end: null },
});
const mockGetFilters = vi.fn().mockResolvedValue({
  triggers: ['4xx', '5xx', 'timeout'],
  sources: ['stoa', 'kong'],
  status_codes: [400, 500, 502, 504],
  resolution_statuses: ['unresolved', 'investigating', 'resolved', 'ignored'],
});

vi.mock('../services/errorSnapshotsApi', () => ({
  errorSnapshotsService: {
    getSnapshots: (...args: unknown[]) => mockGetSnapshots(...args),
    getStats: (...args: unknown[]) => mockGetStats(...args),
    getFilters: (...args: unknown[]) => mockGetFilters(...args),
    getSnapshot: vi.fn().mockResolvedValue(null),
    updateResolution: vi.fn().mockResolvedValue({}),
    generateReplay: vi.fn().mockResolvedValue({ curl_command: 'curl ...' }),
  },
}));

import ErrorSnapshots from './ErrorSnapshots';

function renderComponent() {
  return render(<ErrorSnapshots />);
}

describe('ErrorSnapshots', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetSnapshots.mockResolvedValue({
      items: [
        {
          id: 'SNP-20260115-094512-a1b2c3d4',
          timestamp: '2026-01-15T09:45:12.345Z',
          tenant_id: 'oasis-gunters',
          trigger: '5xx',
          status: 502,
          method: 'POST',
          path: '/api/v1/payments',
          duration_ms: 30042,
          source: 'stoa',
          resolution_status: 'unresolved',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockGetStats.mockResolvedValue({
      total: 15,
      by_trigger: { '5xx': 8, '4xx': 4, timeout: 3 },
      by_status_code: { 500: 5, 502: 3, 400: 4, 504: 3 },
      resolution_stats: { unresolved: 5, investigating: 3, resolved: 6, ignored: 1 },
      period: { start: null, end: null },
    });
    mockGetFilters.mockResolvedValue({
      triggers: ['4xx', '5xx', 'timeout'],
      sources: ['stoa', 'kong'],
      status_codes: [400, 500, 502, 504],
      resolution_statuses: ['unresolved', 'investigating', 'resolved', 'ignored'],
    });
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'Error Snapshots' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(await screen.findByText('Time-travel debugging for gateway errors')).toBeInTheDocument();
  });

  it('shows stats cards after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Total Errors')).toBeInTheDocument();
    });
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('5xx Errors')).toBeInTheDocument();
    expect(screen.getByText('Timeouts')).toBeInTheDocument();
    // 'Resolved' appears in stats card and filter dropdown
    expect(screen.getAllByText('Resolved').length).toBeGreaterThanOrEqual(1);
  });

  it('shows error snapshots list with method and path', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('POST')).toBeInTheDocument();
    });
    expect(screen.getByText('/api/v1/payments')).toBeInTheDocument();
    // '5xx Server Error' trigger badge
    expect(screen.getAllByText('5xx Server Error').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('502')).toBeInTheDocument();
  });

  it('shows gateway source in snapshot row', async () => {
    renderComponent();
    await waitFor(() => {
      // 'stoa' appears in snapshot row and filter dropdown
      expect(screen.getAllByText('stoa').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows Refresh button', async () => {
    renderComponent();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('shows auto-refresh checkbox', async () => {
    renderComponent();
    expect(await screen.findByText('Auto-refresh (10s)')).toBeInTheDocument();
  });

  it('shows filter dropdowns', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('All Triggers')).toBeInTheDocument();
    });
    expect(screen.getByText('All Gateways')).toBeInTheDocument();
    expect(screen.getByText('All Statuses')).toBeInTheDocument();
  });

  it('shows search input', async () => {
    renderComponent();
    expect(await screen.findByPlaceholderText('Search by path...')).toBeInTheDocument();
  });

  it('shows snapshot count in header', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Error Snapshots (1)')).toBeInTheDocument();
    });
  });

  it('shows resolution status badge', async () => {
    renderComponent();
    await waitFor(() => {
      // 'Unresolved' appears in badge and filter dropdown
      expect(screen.getAllByText('Unresolved').length).toBeGreaterThanOrEqual(1);
    });
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(await screen.findByRole('heading', { name: /Error Snapshots/ })).toBeInTheDocument();
      });
    }
  );
});
