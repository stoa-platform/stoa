import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import i18n from 'i18next';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';
import { AuditLog } from './AuditLog';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockGet = vi.fn(() =>
  Promise.resolve({
    data: { entries: [], total: 0, page: 1, page_size: 20, has_more: false },
  })
);

vi.mock('../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

const statsWindow = {
  window_start: '2026-05-01T00:00:00Z',
  window_end: '2026-05-08T00:00:00Z',
};

const emptyListResponse = {
  entries: [],
  total: 0,
  page: 1,
  page_size: 20,
  has_more: false,
};

const emptyStatsResponse = {
  total_events: 0,
  success_count: 0,
  failed_count: 0,
  unique_actors: 0,
  by_action: {},
  by_status: {},
  ...statsWindow,
};

const emptyActionsResponse = {
  actions: [],
  ...statsWindow,
};

function defaultAuditMock(url: unknown) {
  const path = String(url);
  if (path.endsWith('/stats')) {
    return Promise.resolve({ data: emptyStatsResponse });
  }
  if (path.endsWith('/actions')) {
    return Promise.resolve({ data: emptyActionsResponse });
  }
  if (path.includes('/export/')) {
    return Promise.resolve({ data: 'timestamp,action\n' });
  }
  return Promise.resolve({ data: emptyListResponse });
}

describe('AuditLog', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    await i18n.changeLanguage('en');
    localStorage.clear();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGet.mockImplementation(defaultAuditMock);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders title and audit log content', async () => {
    vi.useRealTimers();
    render(<AuditLog />);
    expect(screen.getByText('Audit Log')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
    });
  });

  it('sends start_date and end_date params when date filters are set', async () => {
    vi.useRealTimers();
    render(<AuditLog />);

    await waitFor(() => {
      expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /filters/i }));
    const dateInputs = document.querySelectorAll<HTMLInputElement>('input[type="date"]');
    expect(dateInputs).toHaveLength(2);

    fireEvent.change(dateInputs[0], { target: { value: '2026-05-01' } });
    fireEvent.change(dateInputs[1], { target: { value: '2026-05-07' } });

    await waitFor(() => {
      const dateFilteredCall = mockGet.mock.calls.find(([url, options]) => {
        const params = (options as { params?: Record<string, unknown> } | undefined)?.params;
        return (
          url === '/v1/audit/gregarious-games' &&
          params?.start_date === '2026-05-01' &&
          params?.end_date === '2026-05-07'
        );
      });
      expect(dateFilteredCall).toBeTruthy();

      const params = (dateFilteredCall?.[1] as { params?: Record<string, unknown> })?.params;
      expect(params).not.toHaveProperty('date_from');
      expect(params).not.toHaveProperty('date_to');

      const statsCall = mockGet.mock.calls.find(([url, options]) => {
        const params = (options as { params?: Record<string, unknown> } | undefined)?.params;
        return (
          url === '/v1/audit/gregarious-games/stats' &&
          params?.start_date === '2026-05-01' &&
          params?.end_date === '2026-05-07'
        );
      });
      expect(statsCall).toBeTruthy();
    });
  });

  it('exports with start_date and end_date params when date filters are set', async () => {
    vi.useRealTimers();
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const anchorClickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:audit-log'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    mockGet.mockImplementation((url: unknown) => {
      if (typeof url === 'string' && url.endsWith('/export/csv')) {
        return Promise.resolve({ data: 'timestamp,action\n' });
      }
      return defaultAuditMock(url);
    });

    try {
      render(<AuditLog />);

      await waitFor(() => {
        expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /filters/i }));
      const dateInputs = document.querySelectorAll<HTMLInputElement>('input[type="date"]');
      expect(dateInputs).toHaveLength(2);

      fireEvent.change(dateInputs[0], { target: { value: '2026-05-01' } });
      fireEvent.change(dateInputs[1], { target: { value: '2026-05-07' } });
      fireEvent.click(screen.getByRole('button', { name: /export csv/i }));

      await waitFor(() => {
        const exportCall = mockGet.mock.calls.find(([url]) => String(url).endsWith('/export/csv'));
        expect(exportCall).toBeTruthy();

        const params = (exportCall?.[1] as { params?: Record<string, unknown> })?.params;
        expect(params).toMatchObject({
          start_date: '2026-05-01',
          end_date: '2026-05-07',
        });
        expect(params).not.toHaveProperty('date_from');
        expect(params).not.toHaveProperty('date_to');
      });
    } finally {
      Object.defineProperty(URL, 'createObjectURL', {
        configurable: true,
        value: originalCreateObjectURL,
      });
      Object.defineProperty(URL, 'revokeObjectURL', {
        configurable: true,
        value: originalRevokeObjectURL,
      });
      anchorClickSpy.mockRestore();
    }
  });

  it('stats endpoint populates KPIs and removes page-only subtitles', async () => {
    vi.useRealTimers();
    mockGet.mockImplementation((url: unknown) => {
      if (String(url).endsWith('/stats')) {
        return Promise.resolve({
          data: {
            total_events: 128,
            success_count: 97,
            failed_count: 11,
            unique_actors: 23,
            by_action: { deploy: 44, create: 30 },
            by_status: { success: 97, failure: 11 },
            ...statsWindow,
          },
        });
      }
      return defaultAuditMock(url);
    });

    render(<AuditLog />);

    await waitFor(() => {
      expect(screen.getByText('128')).toBeInTheDocument();
      expect(screen.getByText('97')).toBeInTheDocument();
      expect(screen.getByText('11')).toBeInTheDocument();
      expect(screen.getByText('23')).toBeInTheDocument();
    });
    expect(screen.queryByText(/On this page/i)).not.toBeInTheDocument();
    expect(screen.getAllByText('Last 30 days')).toHaveLength(4);
  });

  it('shows backend warning when audit responses come from demo fallback', async () => {
    vi.useRealTimers();
    mockGet.mockImplementation((url: unknown) => {
      const path = String(url);
      if (path.endsWith('/stats')) {
        return Promise.resolve({
          data: {
            ...emptyStatsResponse,
            source: 'demo',
            warning: 'Audit backend unavailable',
          },
        });
      }
      if (path.endsWith('/actions')) {
        return Promise.resolve({
          data: {
            ...emptyActionsResponse,
            source: 'demo',
            warning: 'Audit backend unavailable',
          },
        });
      }
      return Promise.resolve({
        data: {
          ...emptyListResponse,
          source: 'demo',
          warning: 'Audit backend unavailable',
        },
      });
    });

    render(<AuditLog />);

    await waitFor(() => {
      expect(screen.getByTestId('audit-backend-warning')).toHaveTextContent(
        'Audit backend unavailable'
      );
      expect(screen.getByText('Source: demo')).toBeInTheDocument();
    });
  });

  it('actions endpoint populates filter dynamically by count', async () => {
    vi.useRealTimers();
    mockGet.mockImplementation((url: unknown) => {
      if (String(url).endsWith('/actions')) {
        return Promise.resolve({
          data: {
            actions: [
              { action: 'create', count: 3 },
              { action: 'export', count: 9 },
              { action: 'deploy', count: 6 },
            ],
            ...statsWindow,
          },
        });
      }
      return defaultAuditMock(url);
    });

    render(<AuditLog />);
    await waitFor(() => {
      expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /filters/i }));
    const [actionSelect] = document.querySelectorAll<HTMLSelectElement>('select');
    expect(actionSelect).toBeTruthy();
    expect(Array.from(actionSelect.options).map((option) => option.textContent)).toEqual([
      'All actions',
      'Export (9)',
      'Deploy (6)',
      'Create (3)',
    ]);

    fireEvent.change(actionSelect, { target: { value: 'export' } });

    await waitFor(() => {
      const filteredCall = mockGet.mock.calls.find(([url, options]) => {
        const params = (options as { params?: Record<string, unknown> } | undefined)?.params;
        return url === '/v1/audit/gregarious-games' && params?.action === 'export';
      });
      expect(filteredCall).toBeTruthy();
    });
  });

  it('actor display shows email, display name, then unresolved badge', async () => {
    vi.useRealTimers();
    mockGet.mockImplementation((url: unknown) => {
      if (String(url) === '/v1/audit/gregarious-games') {
        return Promise.resolve({
          data: {
            entries: [
              {
                id: 'evt-email',
                timestamp: '2026-04-04T10:00:00Z',
                user_id: 'user-1',
                user_email: 'alice@acme.com',
                user_display_name: 'Alice Display',
                user_resolved: true,
                action: 'create',
                resource_type: 'api',
                resource_id: 'api-1',
                resource_name: 'api-one',
                status: 'success',
                details: null,
                client_ip: null,
                user_agent: null,
                request_id: null,
                tenant_id: 'acme',
              },
              {
                id: 'evt-display',
                timestamp: '2026-04-04T10:01:00Z',
                user_id: 'user-2',
                user_email: null,
                user_display_name: 'Bob Resolved',
                user_resolved: true,
                action: 'update',
                resource_type: 'api',
                resource_id: 'api-2',
                resource_name: 'api-two',
                status: 'success',
                details: null,
                client_ip: null,
                user_agent: null,
                request_id: null,
                tenant_id: 'acme',
              },
              {
                id: 'evt-unresolved',
                timestamp: '2026-04-04T10:02:00Z',
                user_id: 'svc-agent-001',
                user_email: null,
                user_display_name: null,
                user_resolved: false,
                action: 'deploy',
                resource_type: 'deployment',
                resource_id: 'dep-1',
                resource_name: null,
                status: 'failure',
                details: null,
                client_ip: null,
                user_agent: null,
                request_id: null,
                tenant_id: 'acme',
              },
            ],
            total: 3,
            page: 1,
            page_size: 20,
            has_more: false,
          },
        });
      }
      return defaultAuditMock(url);
    });

    render(<AuditLog />);

    await waitFor(() => {
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
      expect(screen.queryByText('Alice Display')).not.toBeInTheDocument();
      expect(screen.getByText('Bob Resolved')).toBeInTheDocument();
      expect(screen.getByText('svc-agent-001')).toBeInTheDocument();
      expect(screen.getByTestId('actor-unresolved-badge')).toHaveTextContent('unresolved');
    });
  });

  it('shows a visible badge for synthetic audit events', async () => {
    vi.useRealTimers();
    mockGet.mockImplementation((url: unknown) => {
      if (String(url) === '/v1/audit/gregarious-games') {
        return Promise.resolve({
          data: {
            entries: [
              {
                id: 'evt-synthetic',
                timestamp: '2026-05-09T10:00:00Z',
                user_id: 'system-seed',
                user_email: null,
                action: 'export',
                resource_type: 'audit',
                resource_id: 'audit-1',
                resource_name: 'audit-one',
                status: 'success',
                details: {
                  synthetic: true,
                  source: 'seed',
                  fixture_batch: 'observability-data-visibility-2026-05-09',
                },
                is_synthetic: true,
                client_ip: null,
                user_agent: null,
                request_id: 'req-synthetic',
                tenant_id: 'gregarious-games',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
            has_more: false,
          },
        });
      }
      return defaultAuditMock(url);
    });

    render(<AuditLog />);

    await waitFor(() => {
      expect(screen.getByTestId('audit-synthetic-badge')).toHaveTextContent('synthetic');
    });
  });

  it('shows the last successful refresh timestamp', async () => {
    vi.useRealTimers();
    render(<AuditLog />);

    await waitFor(() => {
      expect(screen.getByTestId('audit-refresh-status')).toHaveTextContent(
        /Last refreshed (just now|\d+ min ago)/
      );
    });
  });

  it('backs off on consecutive failures and resets after success', async () => {
    let listAttempts = 0;
    mockGet.mockImplementation((url: unknown) => {
      const path = String(url);
      if (path === '/v1/audit/gregarious-games') {
        listAttempts += 1;
        if (listAttempts <= 2) {
          return Promise.reject({ response: { data: { detail: 'backend unavailable' } } });
        }
        return Promise.resolve({ data: emptyListResponse });
      }
      return defaultAuditMock(url);
    });

    render(<AuditLog />);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText(/retrying in 60s/i)).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(screen.getByText(/retrying in 120s/i)).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
      await Promise.resolve();
    });
    expect(screen.queryByText(/Refresh failed/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('audit-refresh-status')).toHaveTextContent(/Last refreshed/);

    const attemptsAfterReset = listAttempts;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29_000);
    });
    expect(listAttempts).toBe(attemptsAfterReset);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(listAttempts).toBe(attemptsAfterReset + 1);
  });

  it('split-button exports call csv and json endpoints', async () => {
    vi.useRealTimers();
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const anchorClickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:audit-log'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    mockGet.mockImplementation((url: unknown) => {
      if (String(url).includes('/export/csv')) {
        return Promise.resolve({ data: 'timestamp,action\n' });
      }
      if (String(url).includes('/export/json')) {
        return Promise.resolve({ data: [{ action: 'deploy' }] });
      }
      return defaultAuditMock(url);
    });

    try {
      render(<AuditLog />);
      await waitFor(() => {
        expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /export csv/i }));
      await waitFor(() => {
        expect(mockGet.mock.calls.some(([url]) => String(url).endsWith('/export/csv'))).toBe(true);
      });

      fireEvent.click(screen.getByRole('button', { name: /export options/i }));
      fireEvent.click(screen.getByRole('button', { name: /export json/i }));
      await waitFor(() => {
        expect(mockGet.mock.calls.some(([url]) => String(url).endsWith('/export/json'))).toBe(true);
      });
    } finally {
      Object.defineProperty(URL, 'createObjectURL', {
        configurable: true,
        value: originalCreateObjectURL,
      });
      Object.defineProperty(URL, 'revokeObjectURL', {
        configurable: true,
        value: originalRevokeObjectURL,
      });
      anchorClickSpy.mockRestore();
    }
  });

  it('locale switcher language changes timestamp formatting', async () => {
    vi.useRealTimers();
    const timestamp = '2026-05-04T13:05:06Z';
    const formatOptions = {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    } as const;
    mockGet.mockImplementation((url: unknown) => {
      if (String(url) === '/v1/audit/gregarious-games') {
        return Promise.resolve({
          data: {
            entries: [
              {
                id: 'evt-locale',
                timestamp,
                user_id: 'user-123',
                user_email: 'alice@acme.com',
                action: 'create',
                resource_type: 'api',
                resource_id: 'api-456',
                resource_name: 'my-api',
                status: 'success',
                details: null,
                client_ip: null,
                user_agent: null,
                request_id: null,
                tenant_id: 'acme',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
            has_more: false,
          },
        });
      }
      return defaultAuditMock(url);
    });

    render(<AuditLog />);

    const expectedEnglish = new Date(timestamp).toLocaleString('en', formatOptions);
    await waitFor(() => {
      expect(screen.getByText(expectedEnglish)).toBeInTheDocument();
    });

    await act(async () => {
      await i18n.changeLanguage('fr');
    });

    const expectedFrench = new Date(timestamp).toLocaleString('fr', formatOptions);
    await waitFor(() => {
      expect(screen.getByText(expectedFrench)).toBeInTheDocument();
    });
  });

  it('clears polling interval on unmount and does not update state after unmount', async () => {
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');

    const { unmount } = render(<AuditLog />);

    // Wait for initial data load
    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });

    // Record call count before unmount
    const callsBefore = mockGet.mock.calls.length;

    // Unmount — should clear interval and set mountedRef.current = false
    unmount();

    // clearInterval should have been called during cleanup
    expect(clearIntervalSpy.mock.calls.length).toBeGreaterThan(0);

    // Advance timers past what would be the next polling interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(35_000);
    });

    // After unmount, no new API calls should have been made by the interval
    // The interval was cleared, so mockGet should not have been called again
    expect(mockGet.mock.calls.length).toBe(callsBefore);

    clearIntervalSpy.mockRestore();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.useRealTimers();
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<AuditLog />);
        expect(screen.getByText('Audit Log')).toBeInTheDocument();
        await waitFor(() => {
          expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
        });
      });
    }
  );

  // Export button visibility per role
  describe('Export button RBAC', () => {
    it.each<PersonaRole>(['cpi-admin', 'tenant-admin'])(
      'shows Export button for %s',
      async (role) => {
        vi.useRealTimers();
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<AuditLog />);
        await waitFor(() => {
          expect(screen.getByText('Export CSV')).toBeInTheDocument();
        });
      }
    );

    it.each<PersonaRole>(['devops', 'viewer'])('hides Export button for %s', async (role) => {
      vi.useRealTimers();
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      render(<AuditLog />);
      await waitFor(() => {
        expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
      });
      expect(screen.queryByText('Export CSV')).not.toBeInTheDocument();
    });
  });

  // Field mapping: API returns user_email/client_ip, verify rendered
  describe('Field mapping', () => {
    it('renders user_email in Actor column', async () => {
      vi.useRealTimers();
      mockGet.mockImplementation(() =>
        Promise.resolve({
          data: {
            entries: [
              {
                id: 'evt-1',
                timestamp: '2026-04-04T10:00:00Z',
                user_id: 'user-123',
                user_email: 'alice@acme.com',
                action: 'create',
                resource_type: 'api',
                resource_id: 'api-456',
                resource_name: 'my-api',
                status: 'success',
                details: null,
                client_ip: '192.168.1.100',
                user_agent: 'Mozilla/5.0',
                request_id: 'req-789',
                tenant_id: 'acme',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
            has_more: false,
          },
        })
      );

      render(<AuditLog />);
      await waitFor(() => {
        expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
      });
    });

    it('falls back to user_id when user_email is null', async () => {
      vi.useRealTimers();
      mockGet.mockImplementation(() =>
        Promise.resolve({
          data: {
            entries: [
              {
                id: 'evt-2',
                timestamp: '2026-04-04T10:00:00Z',
                user_id: 'svc-agent-001',
                user_email: null,
                action: 'update',
                resource_type: 'tool',
                resource_id: 'tool-789',
                resource_name: null,
                status: 'success',
                details: null,
                client_ip: null,
                user_agent: null,
                request_id: null,
                tenant_id: 'acme',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
            has_more: false,
          },
        })
      );

      render(<AuditLog />);
      await waitFor(() => {
        expect(screen.getByText('svc-agent-001')).toBeInTheDocument();
      });
    });

    it('shows "system" when both user_email and user_id are null', async () => {
      vi.useRealTimers();
      mockGet.mockImplementation(() =>
        Promise.resolve({
          data: {
            entries: [
              {
                id: 'evt-3',
                timestamp: '2026-04-04T10:00:00Z',
                user_id: null,
                user_email: null,
                action: 'config_change',
                resource_type: 'system',
                resource_id: null,
                resource_name: null,
                status: 'success',
                details: null,
                client_ip: null,
                user_agent: null,
                request_id: null,
                tenant_id: 'acme',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
            has_more: false,
          },
        })
      );

      render(<AuditLog />);
      await waitFor(() => {
        expect(screen.getByText('system')).toBeInTheDocument();
      });
    });
  });
});
