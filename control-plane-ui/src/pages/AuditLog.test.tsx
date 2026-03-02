import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
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
});
