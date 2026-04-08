/**
 * Spec tests for CAB-2004: LogExplorer component
 *
 * Generated from SPEC.md acceptance criteria (AC9-AC15).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock auth context
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock SubNav (navigation component)
vi.mock('../../components/SubNav', () => ({
  SubNav: () => null,
}));

// Mock react-router-dom's useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock apiService
const mockGet = vi.fn();
vi.mock('../../services/api', () => ({
  apiService: { get: (...args: unknown[]) => mockGet(...args) },
}));

const mockLogsResponse = {
  logs: [
    {
      timestamp: '2026-04-07T12:00:00Z',
      service: 'stoa-gateway',
      level: 'info',
      message: 'request completed',
      trace_id: 'abc123',
      tenant_id: 'acme',
      request_id: 'req-001',
      duration_ms: 42.5,
      path: '/mcp/tools/list',
      method: 'GET',
      status_code: 200,
      consumer_id: 'consumer-789',
    },
    {
      timestamp: '2026-04-07T12:01:00Z',
      service: 'control-plane-api',
      level: 'error',
      message: 'auth failed',
      trace_id: 'def456',
      tenant_id: 'acme',
      request_id: 'req-002',
      duration_ms: 5.0,
      path: '/v1/apis',
      method: 'POST',
      status_code: 401,
      consumer_id: null,
    },
  ],
  total: 2,
  limit: 50,
  has_more: false,
  query_time_ms: 120,
};

function mockApiSuccess(data = mockLogsResponse) {
  mockGet.mockResolvedValue({ data });
}

function mockApiError(status: number) {
  mockGet.mockRejectedValue({ response: { status } });
}

async function renderLogExplorer() {
  const { LogExplorer } = await import('../../pages/RequestExplorer/LogExplorer');
  return render(
    <MemoryRouter>
      <LogExplorer />
    </MemoryRouter>
  );
}

describe('spec/CAB-2004: LogExplorer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers(); // Ensure real timers before each test
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  afterEach(() => {
    vi.useRealTimers(); // Safety: always restore real timers
  });

  describe('AC9: Log table rendering', () => {
    it('renders log entries with timestamp, service badge, level badge, message, duration', async () => {
      mockApiSuccess();
      await renderLogExplorer();

      await waitFor(() => {
        expect(screen.getByText('request completed')).toBeInTheDocument();
        expect(screen.getByText('auth failed')).toBeInTheDocument();
      });

      expect(screen.getByText('stoa-gateway')).toBeInTheDocument();
      expect(screen.getByText('control-plane-api')).toBeInTheDocument();
      expect(screen.getByText('info')).toBeInTheDocument();
      expect(screen.getByText('error')).toBeInTheDocument();
      expect(screen.getByText(/42\.5/)).toBeInTheDocument();
    });
  });

  describe('AC10: Log detail panel', () => {
    it('clicking a log row opens detail panel showing full JSON fields', async () => {
      mockApiSuccess();
      await renderLogExplorer();

      await waitFor(() => {
        expect(screen.getByText('request completed')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('request completed'));

      await waitFor(() => {
        expect(screen.getByText('abc123')).toBeInTheDocument();
        expect(screen.getByText('req-001')).toBeInTheDocument();
        expect(screen.getByText('consumer-789')).toBeInTheDocument();
        expect(screen.getByText('/mcp/tools/list')).toBeInTheDocument();
      });
    });
  });

  describe('AC11: Trace link navigation', () => {
    it('clicking trace_id navigates to /call-flow/trace/{trace_id}', async () => {
      mockApiSuccess();
      await renderLogExplorer();

      await waitFor(() => {
        expect(screen.getByText('request completed')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('request completed'));

      await waitFor(() => {
        const traceLink = screen.getByText('abc123');
        fireEvent.click(traceLink);
        expect(mockNavigate).toHaveBeenCalledWith('/call-flow/trace/abc123');
      });
    });
  });

  describe('AC12: Auto-refresh toggle', () => {
    it('auto-refresh toggle works with selectable intervals', async () => {
      vi.useFakeTimers();
      mockApiSuccess();

      await act(async () => {
        await renderLogExplorer();
      });

      // Wait for initial render to settle
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });

      const refreshToggle = screen.getByRole('combobox', { name: /refresh/i });
      const callCountBefore = mockGet.mock.calls.length;

      await act(async () => {
        fireEvent.change(refreshToggle, { target: { value: '5' } });
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5100);
      });

      expect(mockGet.mock.calls.length).toBeGreaterThan(callCountBefore);
    });

    it('cleans up timer on unmount (no memory leak)', async () => {
      vi.useFakeTimers();
      mockApiSuccess();

      let unmount: () => void;
      await act(async () => {
        const result = await renderLogExplorer();
        unmount = result.unmount;
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });

      const refreshToggle = screen.getByRole('combobox', { name: /refresh/i });
      await act(async () => {
        fireEvent.change(refreshToggle, { target: { value: '5' } });
      });

      unmount!();

      const callCountAfterUnmount = mockGet.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      expect(mockGet.mock.calls.length).toBe(callCountAfterUnmount);
    });
  });

  describe('AC13: Empty state', () => {
    it('shows empty state when 0 results', async () => {
      mockApiSuccess({
        logs: [],
        total: 0,
        limit: 50,
        has_more: false,
        query_time_ms: 50,
      });

      await renderLogExplorer();

      await waitFor(() => {
        expect(screen.getByText(/no logs found/i)).toBeInTheDocument();
      });
    });

    it('shows unavailable banner when Loki returns 503', async () => {
      mockApiError(503);

      await renderLogExplorer();

      await waitFor(() => {
        expect(screen.getByText(/loki unavailable/i)).toBeInTheDocument();
      });
    });
  });

  describe('AC14: Navigation tab renamed', () => {
    it('navigation shows "Gateway Logs" instead of "Logs"', async () => {
      const { observabilityTabs } = await import('../../components/subNavGroups');
      const logsTab = observabilityTabs.find((tab: { href: string }) => tab.href === '/logs');
      expect(logsTab).toBeDefined();
      expect(logsTab!.label).toBe('Gateway Logs');
    });
  });

  describe('AC15: Dead code cleanup', () => {
    it('LogsEmbed is not exported from RequestExplorer index', async () => {
      const mod = await import('../../pages/RequestExplorer');
      expect(mod).not.toHaveProperty('LogsEmbed');
    });
  });

  describe('Filter controls', () => {
    it('renders service dropdown, search input, and time range', async () => {
      mockApiSuccess();
      await renderLogExplorer();

      await waitFor(() => {
        expect(screen.getByRole('combobox', { name: /service/i })).toBeInTheDocument();
      });

      expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
      expect(screen.getByText('1h')).toBeInTheDocument();
      expect(screen.getByText('6h')).toBeInTheDocument();
      expect(screen.getByText('24h')).toBeInTheDocument();
    });

    it('service filter triggers API call with service param', async () => {
      mockApiSuccess();
      await renderLogExplorer();

      await waitFor(() => {
        expect(screen.getByRole('combobox', { name: /service/i })).toBeInTheDocument();
      });

      const serviceDropdown = screen.getByRole('combobox', { name: /service/i });

      await act(async () => {
        fireEvent.change(serviceDropdown, { target: { value: 'gateway' } });
      });

      await waitFor(() => {
        const lastCall = mockGet.mock.calls[mockGet.mock.calls.length - 1];
        expect(lastCall[1]?.params?.service).toBe('gateway');
      });
    });
  });

  describe('RBAC rendering', () => {
    it.each<PersonaRole>(['cpi-admin', 'tenant-admin'])(
      '%s can access LogExplorer',
      async (role) => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        mockApiSuccess();

        await renderLogExplorer();

        await waitFor(() => {
          expect(screen.getByText(/gateway logs/i)).toBeInTheDocument();
        });
      }
    );
  });
});
