import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { PermissionGate } from './PermissionGate';
import { createAuthMock, renderWithProviders, type PersonaRole } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PermissionGate', () => {
  describe('permission-based gating', () => {
    it('renders children when user has the required permission', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(
        <PermissionGate permission="tenants:read">
          <div>Admin Content</div>
        </PermissionGate>
      );

      expect(screen.getByText('Admin Content')).toBeInTheDocument();
    });

    it('hides children when user lacks the required permission', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(
        <PermissionGate permission="tenants:read">
          <div>Admin Content</div>
        </PermissionGate>
      );

      expect(screen.queryByText('Admin Content')).not.toBeInTheDocument();
    });

    it('renders fallback when user lacks permission', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(
        <PermissionGate permission="tenants:read" fallback={<div>Access Denied</div>}>
          <div>Admin Content</div>
        </PermissionGate>
      );

      expect(screen.queryByText('Admin Content')).not.toBeInTheDocument();
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });

    it('renders nothing (no fallback) when unauthorized by default', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));

      const { container } = renderWithProviders(
        <PermissionGate permission="tenants:create">
          <div>Secret</div>
        </PermissionGate>
      );

      expect(screen.queryByText('Secret')).not.toBeInTheDocument();
      expect(container.innerHTML).toBe('');
    });
  });

  describe('role-based gating', () => {
    it('renders children when user has the required role', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(
        <PermissionGate role="cpi-admin">
          <div>Admin Panel</div>
        </PermissionGate>
      );

      expect(screen.getByText('Admin Panel')).toBeInTheDocument();
    });

    it('hides children when user does not have the required role', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('devops'));

      renderWithProviders(
        <PermissionGate role="cpi-admin">
          <div>Admin Panel</div>
        </PermissionGate>
      );

      expect(screen.queryByText('Admin Panel')).not.toBeInTheDocument();
    });
  });

  describe('combined permission + role', () => {
    it('renders when both permission and role match', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(
        <PermissionGate permission="tenants:read" role="cpi-admin">
          <div>Full Access</div>
        </PermissionGate>
      );

      expect(screen.getByText('Full Access')).toBeInTheDocument();
    });

    it('hides when permission matches but role does not', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(
        <PermissionGate permission="tenants:read" role="tenant-admin">
          <div>Full Access</div>
        </PermissionGate>
      );

      expect(screen.queryByText('Full Access')).not.toBeInTheDocument();
    });
  });

  describe('no constraints', () => {
    it('renders children when neither permission nor role is specified', () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(
        <PermissionGate>
          <div>Public Content</div>
        </PermissionGate>
      );

      expect(screen.getByText('Public Content')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      });

      it(`${role} sees apis:read content`, () => {
        renderWithProviders(
          <PermissionGate permission="apis:read">
            <div>API Content</div>
          </PermissionGate>
        );

        // All 4 roles have apis:read
        expect(screen.getByText('API Content')).toBeInTheDocument();
      });

      it(`${role} ${role === 'cpi-admin' ? 'sees' : 'does not see'} tenants:read content`, () => {
        renderWithProviders(
          <PermissionGate permission="tenants:read">
            <div>Tenant Content</div>
          </PermissionGate>
        );

        if (role === 'cpi-admin') {
          expect(screen.getByText('Tenant Content')).toBeInTheDocument();
        } else {
          expect(screen.queryByText('Tenant Content')).not.toBeInTheDocument();
        }
      });
    }
  );
});
