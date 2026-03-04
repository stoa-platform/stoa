/**
 * Tests for ProfilePage (CAB-1133)
 *
 * View and manage account settings.
 * Page-level functional tests covering all personas.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { ProfilePage } from '../profile/Profile';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const personaData: Record<
  PersonaRole,
  { name: string; email: string; org: string; userId: string }
> = {
  'cpi-admin': {
    name: 'James Halliday',
    email: 'halliday@gregarious-games.com',
    org: 'Gregarious Games',
    userId: 'user-halliday',
  },
  'tenant-admin': {
    name: 'Wade Watts',
    email: 'parzival@oasis-gunters.com',
    org: 'OASIS Gunters',
    userId: 'user-parzival',
  },
  devops: {
    name: 'Samantha Cook',
    email: 'art3mis@oasis-gunters.com',
    org: 'OASIS Gunters',
    userId: 'user-art3mis',
  },
  viewer: {
    name: 'Helen Harris',
    email: 'aech@oasis-gunters.com',
    org: 'OASIS Gunters',
    userId: 'user-aech',
  },
};

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'ProfilePage — %s persona',
  (role) => {
    beforeEach(() => {
      vi.clearAllMocks();
      mockUseAuth.mockReturnValue(createAuthMock(role));
    });

    describe('Page Structure', () => {
      it('should render page title and subtitle', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText('My Profile')).toBeInTheDocument();
        expect(screen.getByText('View and manage your account settings')).toBeInTheDocument();
      });

      it('should render user name in header', () => {
        renderWithProviders(<ProfilePage />);

        const names = screen.getAllByText(personaData[role].name);
        expect(names.length).toBeGreaterThan(0);
      });

      it('should render user email in header', () => {
        renderWithProviders(<ProfilePage />);

        const emails = screen.getAllByText(personaData[role].email);
        expect(emails.length).toBeGreaterThan(0);
      });
    });

    describe('Account Information Section', () => {
      it('should show Full Name field', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText('Full Name')).toBeInTheDocument();
        const names = screen.getAllByText(personaData[role].name);
        expect(names.length).toBeGreaterThan(0);
      });

      it('should show Email field', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText('Email')).toBeInTheDocument();
        const emails = screen.getAllByText(personaData[role].email);
        expect(emails.length).toBeGreaterThan(0);
      });

      it('should show Organization field', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText('Organization')).toBeInTheDocument();
        const orgs = screen.getAllByText(personaData[role].org);
        expect(orgs.length).toBeGreaterThan(0);
      });
    });

    describe('Security Section', () => {
      it('should show User ID field', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText('User ID')).toBeInTheDocument();
        expect(screen.getByText(personaData[role].userId)).toBeInTheDocument();
      });

      it('should show Authentication method', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText('Authentication')).toBeInTheDocument();
        expect(screen.getByText('OIDC (Keycloak)')).toBeInTheDocument();
      });
    });

    describe('API Keys Section', () => {
      it('should render API Keys section', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText('API Keys')).toBeInTheDocument();
      });

      it('should show placeholder text for API keys', () => {
        renderWithProviders(<ProfilePage />);

        expect(screen.getByText(/API key management will be available soon/)).toBeInTheDocument();
      });
    });
  }
);
