import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../contexts/AuthContext';
import { UnauthorizedPage } from './Unauthorized';

describe('UnauthorizedPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
  });

  it('renders access denied heading', () => {
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.getByRole('heading', { name: /access denied/i })).toBeInTheDocument();
  });

  it('renders permission error description', () => {
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.getByText(/you don't have permission to access this page/i)).toBeInTheDocument();
  });

  it('shows user email in debug info', () => {
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.getByText('aech@oasis-gunters.com')).toBeInTheDocument();
  });

  it('shows user roles in debug info', () => {
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.getByText('viewer')).toBeInTheDocument();
  });

  it('shows tenant in debug info', () => {
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.getByText('oasis-gunters')).toBeInTheDocument();
  });

  it('renders "Go to Dashboard" link pointing to /', () => {
    renderWithProviders(<UnauthorizedPage />);
    const link = screen.getByRole('link', { name: /go to dashboard/i });
    expect(link).toHaveAttribute('href', '/');
  });

  it('renders "Go Back" button', () => {
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.getByRole('button', { name: /go back/i })).toBeInTheDocument();
  });

  it('does not render debug info when user is null', () => {
    vi.mocked(useAuth).mockReturnValue({
      ...createAuthMock('viewer'),
      user: null as never,
    });
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.queryByText(/current user information/i)).not.toBeInTheDocument();
  });

  it('shows "none" when user has no roles', () => {
    vi.mocked(useAuth).mockReturnValue({
      ...createAuthMock('viewer'),
      user: { ...createAuthMock('viewer').user, roles: [] },
    });
    renderWithProviders(<UnauthorizedPage />);
    expect(screen.getByText('none')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      it('renders the page with user info', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<UnauthorizedPage />);
        expect(screen.getByRole('heading', { name: /access denied/i })).toBeInTheDocument();
      });
    }
  );
});
