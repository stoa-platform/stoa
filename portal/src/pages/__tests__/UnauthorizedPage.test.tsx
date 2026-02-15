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

describe('UnauthorizedPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('renders "Access Denied" heading', () => {
    renderWithProviders(<UnauthorizedPage />);

    expect(screen.getByText('Access Denied')).toBeInTheDocument();
    expect(screen.getByText(/You don't have permission to access this page/)).toBeInTheDocument();
  });

  it('displays current user info for debugging', () => {
    mockAuth.mockReturnValue(createAuthMock('devops'));

    renderWithProviders(<UnauthorizedPage />);

    expect(screen.getByText('Current user information:')).toBeInTheDocument();
    expect(screen.getByText('art3mis@oasis-gunters.com')).toBeInTheDocument();
    expect(screen.getByText('devops')).toBeInTheDocument();
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
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<UnauthorizedPage />);

    expect(screen.getByText('oasis-gunters')).toBeInTheDocument();
  });

  describe('Persona-based Tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(personas)('%s can view the unauthorized page', (persona) => {
      mockAuth.mockReturnValue(createAuthMock(persona));

      renderWithProviders(<UnauthorizedPage />);

      expect(screen.getByText('Access Denied')).toBeInTheDocument();
      expect(screen.getByText('Go to Dashboard')).toBeInTheDocument();
    });
  });
});
