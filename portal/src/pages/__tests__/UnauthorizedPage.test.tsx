/**
 * UnauthorizedPage Tests - CAB-1133
 *
 * Tests for the "Access Denied" page shown when a user lacks permissions.
 * No route guard — accessible to all authenticated users.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { UnauthorizedPage } from '../Unauthorized';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';

// Mock AuthContext
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

const personaEmails: Record<PersonaRole, string> = {
  'cpi-admin': 'halliday@gregarious-games.com',
  'tenant-admin': 'parzival@oasis-gunters.com',
  'devops': 'art3mis@oasis-gunters.com',
  'viewer': 'aech@oasis-gunters.com',
};

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'UnauthorizedPage — %s persona',
  (role) => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock(role));
  });

  it('renders "Access Denied" heading', () => {
    renderWithProviders(<UnauthorizedPage />);

    expect(screen.getByText('Access Denied')).toBeInTheDocument();
    expect(screen.getByText(/You don't have permission to access this page/)).toBeInTheDocument();
  });

  it('displays current user info for debugging', () => {
    renderWithProviders(<UnauthorizedPage />);

    expect(screen.getByText('Current user information:')).toBeInTheDocument();
    expect(screen.getByText(personaEmails[role])).toBeInTheDocument();
  });

  it('renders "Go to Dashboard" link', () => {
    renderWithProviders(<UnauthorizedPage />);

    const dashboardLink = screen.getByRole('link', { name: /Go to Dashboard/ });
    expect(dashboardLink).toBeInTheDocument();
    expect(dashboardLink).toHaveAttribute('href', '/');
  });

  it('renders "Go Back" button', () => {
    renderWithProviders(<UnauthorizedPage />);

    expect(screen.getByText('Go Back')).toBeInTheDocument();
  });

  it('shows tenant_id when user has one', () => {
    renderWithProviders(<UnauthorizedPage />);

    if (role === 'cpi-admin') {
      // cpi-admin has tenant_id 'gregarious-games'
      expect(screen.getByText('gregarious-games')).toBeInTheDocument();
    } else {
      expect(screen.getByText('oasis-gunters')).toBeInTheDocument();
    }
  });
});
