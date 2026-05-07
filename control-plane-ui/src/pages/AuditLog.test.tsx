import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
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

describe('AuditLog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    localStorage.clear();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGet.mockImplementation(() =>
      Promise.resolve({
        data: { entries: [], total: 0, page: 1, page_size: 20, has_more: false },
      })
    );
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
      return Promise.resolve({
        data: { entries: [], total: 0, page: 1, page_size: 20, has_more: false },
      });
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
      fireEvent.click(screen.getByRole('button', { name: /export/i }));

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
      it('renders the page', () => {
        vi.useRealTimers();
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<AuditLog />);
        expect(screen.getByText('Audit Log')).toBeInTheDocument();
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
          expect(screen.getByText('Export')).toBeInTheDocument();
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
      expect(screen.queryByText('Export')).not.toBeInTheDocument();
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
