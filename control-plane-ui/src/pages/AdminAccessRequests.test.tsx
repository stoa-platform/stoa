import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AdminAccessRequests } from './AdminAccessRequests';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../hooks/useAccessRequests', () => ({
  useAccessRequests: vi.fn(() => ({
    data: { data: [], total: 0 },
    isLoading: false,
    error: null,
  })),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('AdminAccessRequests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the page title for cpi-admin', () => {
    renderWithQuery(<AdminAccessRequests />);
    expect(screen.getByText('Access Requests')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderWithQuery(<AdminAccessRequests />);
    expect(
      screen.getByText('Enterprise access requests from the Developer Portal')
    ).toBeInTheDocument();
  });

  it('shows status filter', () => {
    renderWithQuery(<AdminAccessRequests />);
    expect(screen.getByDisplayValue('All statuses')).toBeInTheDocument();
  });

  it('shows empty state when no requests', () => {
    renderWithQuery(<AdminAccessRequests />);
    expect(screen.getByText('No access requests found')).toBeInTheDocument();
  });

  it('shows access denied for non-admin roles', () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
    renderWithQuery(<AdminAccessRequests />);
    expect(screen.getByText('Access Denied')).toBeInTheDocument();
  });

  it('shows access denied for devops', () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('devops'));
    renderWithQuery(<AdminAccessRequests />);
    expect(screen.getByText('Access Denied')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithQuery(<AdminAccessRequests />);
        // cpi-admin sees the page, others see Access Denied
        if (role === 'cpi-admin') {
          expect(screen.getByText('Access Requests')).toBeInTheDocument();
        } else {
          expect(screen.getByText('Access Denied')).toBeInTheDocument();
        }
      });
    }
  );
});
