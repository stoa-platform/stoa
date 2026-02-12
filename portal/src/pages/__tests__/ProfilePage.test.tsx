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

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  describe('Page Structure', () => {
    it('should render page title and subtitle', () => {
      renderWithProviders(<ProfilePage />);

      expect(screen.getByText('My Profile')).toBeInTheDocument();
      expect(screen.getByText('View and manage your account settings')).toBeInTheDocument();
    });

    it('should render user name in header', () => {
      renderWithProviders(<ProfilePage />);

      const names = screen.getAllByText('Wade Watts');
      expect(names.length).toBeGreaterThan(0);
    });

    it('should render user email in header', () => {
      renderWithProviders(<ProfilePage />);

      const emails = screen.getAllByText('parzival@oasis-gunters.com');
      expect(emails.length).toBeGreaterThan(0);
    });
  });

  describe('Account Information Section', () => {
    it('should show Full Name field', () => {
      renderWithProviders(<ProfilePage />);

      expect(screen.getByText('Full Name')).toBeInTheDocument();
      const names = screen.getAllByText('Wade Watts');
      expect(names.length).toBeGreaterThan(0);
    });

    it('should show Email field', () => {
      renderWithProviders(<ProfilePage />);

      expect(screen.getByText('Email')).toBeInTheDocument();
      const emails = screen.getAllByText('parzival@oasis-gunters.com');
      expect(emails.length).toBeGreaterThan(0);
    });

    it('should show Organization field', () => {
      renderWithProviders(<ProfilePage />);

      expect(screen.getByText('Organization')).toBeInTheDocument();
      const orgs = screen.getAllByText('OASIS Gunters');
      expect(orgs.length).toBeGreaterThan(0);
    });
  });

  describe('Security Section', () => {
    it('should show User ID field', () => {
      renderWithProviders(<ProfilePage />);

      expect(screen.getByText('User ID')).toBeInTheDocument();
      expect(screen.getByText('user-parzival')).toBeInTheDocument();
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

  describe('Persona-based Tests', () => {
    it('should render cpi-admin profile (James Halliday)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(<ProfilePage />);

      const names = screen.getAllByText('James Halliday');
      expect(names.length).toBeGreaterThan(0);
      const emails = screen.getAllByText('halliday@gregarious-games.com');
      expect(emails.length).toBeGreaterThan(0);
      expect(screen.getByText('Gregarious Games')).toBeInTheDocument();
      expect(screen.getByText('user-halliday')).toBeInTheDocument();
    });

    it('should render tenant-admin profile (Wade Watts)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));

      renderWithProviders(<ProfilePage />);

      const names = screen.getAllByText('Wade Watts');
      expect(names.length).toBeGreaterThan(0);
      const emails = screen.getAllByText('parzival@oasis-gunters.com');
      expect(emails.length).toBeGreaterThan(0);
      const orgs = screen.getAllByText('OASIS Gunters');
      expect(orgs.length).toBeGreaterThan(0);
      expect(screen.getByText('user-parzival')).toBeInTheDocument();
    });

    it('should render devops profile (Samantha Cook)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('devops'));

      renderWithProviders(<ProfilePage />);

      const names = screen.getAllByText('Samantha Cook');
      expect(names.length).toBeGreaterThan(0);
      const emails = screen.getAllByText('art3mis@oasis-gunters.com');
      expect(emails.length).toBeGreaterThan(0);
      const orgs = screen.getAllByText('OASIS Gunters');
      expect(orgs.length).toBeGreaterThan(0);
      expect(screen.getByText('user-art3mis')).toBeInTheDocument();
    });

    it('should render viewer profile (Helen Harris)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(<ProfilePage />);

      const names = screen.getAllByText('Helen Harris');
      expect(names.length).toBeGreaterThan(0);
      const emails = screen.getAllByText('aech@oasis-gunters.com');
      expect(emails.length).toBeGreaterThan(0);
      const orgs = screen.getAllByText('OASIS Gunters');
      expect(orgs.length).toBeGreaterThan(0);
      expect(screen.getByText('user-aech')).toBeInTheDocument();
    });
  });
});
