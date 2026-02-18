/**
 * Tests for PermissionGate component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PermissionGate, withPermission } from './PermissionGate';

// Mock AuthContext
/* eslint-disable jsx-a11y/aria-role */
const mockAuth = {
  user: null as any,
  isAuthenticated: true,
  isLoading: false,
  isReady: true,
  accessToken: 'token',
  hasPermission: vi.fn(),
  hasAnyPermission: vi.fn(),
  hasAllPermissions: vi.fn(),
  hasRole: vi.fn(),
  hasScope: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  refreshPermissions: vi.fn(),
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth,
}));

describe('PermissionGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.hasPermission.mockReturnValue(true);
    mockAuth.hasAnyPermission.mockReturnValue(true);
    mockAuth.hasAllPermissions.mockReturnValue(true);
    mockAuth.hasRole.mockReturnValue(true);
    mockAuth.hasScope.mockReturnValue(true);
  });

  describe('single permission', () => {
    it('should render children when permission is granted', () => {
      mockAuth.hasPermission.mockReturnValue(true);

      render(
        <PermissionGate permission="apis:create">
          <span>Create API</span>
        </PermissionGate>
      );

      expect(screen.getByText('Create API')).toBeInTheDocument();
    });

    it('should not render children when permission is denied', () => {
      mockAuth.hasPermission.mockReturnValue(false);

      render(
        <PermissionGate permission="apis:delete">
          <span>Delete API</span>
        </PermissionGate>
      );

      expect(screen.queryByText('Delete API')).not.toBeInTheDocument();
    });

    it('should render fallback when permission is denied', () => {
      mockAuth.hasPermission.mockReturnValue(false);

      render(
        <PermissionGate permission="apis:delete" fallback={<span>No access</span>}>
          <span>Delete API</span>
        </PermissionGate>
      );

      expect(screen.queryByText('Delete API')).not.toBeInTheDocument();
      expect(screen.getByText('No access')).toBeInTheDocument();
    });
  });

  describe('multiple permissions (OR)', () => {
    it('should render when any permission matches', () => {
      mockAuth.hasAnyPermission.mockReturnValue(true);

      render(
        <PermissionGate permissions={['apis:create', 'apis:update']}>
          <span>Edit</span>
        </PermissionGate>
      );

      expect(screen.getByText('Edit')).toBeInTheDocument();
    });

    it('should not render when no permissions match', () => {
      mockAuth.hasAnyPermission.mockReturnValue(false);

      render(
        <PermissionGate permissions={['apis:create', 'apis:update']}>
          <span>Edit</span>
        </PermissionGate>
      );

      expect(screen.queryByText('Edit')).not.toBeInTheDocument();
    });
  });

  describe('multiple permissions (AND)', () => {
    it('should render when all permissions match', () => {
      mockAuth.hasAllPermissions.mockReturnValue(true);

      render(
        <PermissionGate permissions={['apis:create', 'apis:deploy']} requireAll>
          <span>Deploy</span>
        </PermissionGate>
      );

      expect(screen.getByText('Deploy')).toBeInTheDocument();
    });

    it('should not render when not all permissions match', () => {
      mockAuth.hasAllPermissions.mockReturnValue(false);

      render(
        <PermissionGate permissions={['apis:create', 'apis:deploy']} requireAll>
          <span>Deploy</span>
        </PermissionGate>
      );

      expect(screen.queryByText('Deploy')).not.toBeInTheDocument();
    });
  });

  describe('role check', () => {
    it('should render when role matches', () => {
      mockAuth.hasRole.mockReturnValue(true);

      render(
        <PermissionGate role="cpi-admin">
          <span>Admin Panel</span>
        </PermissionGate>
      );

      expect(screen.getByText('Admin Panel')).toBeInTheDocument();
    });

    it('should not render when role does not match', () => {
      mockAuth.hasRole.mockReturnValue(false);

      render(
        <PermissionGate role="cpi-admin">
          <span>Admin Panel</span>
        </PermissionGate>
      );

      expect(screen.queryByText('Admin Panel')).not.toBeInTheDocument();
    });
  });

  describe('scope check', () => {
    it('should render when scope matches', () => {
      mockAuth.hasScope.mockReturnValue(true);

      render(
        <PermissionGate scope="stoa:catalog:write">
          <span>Catalog Editor</span>
        </PermissionGate>
      );

      expect(screen.getByText('Catalog Editor')).toBeInTheDocument();
    });

    it('should not render when scope does not match', () => {
      mockAuth.hasScope.mockReturnValue(false);

      render(
        <PermissionGate scope="stoa:catalog:write">
          <span>Catalog Editor</span>
        </PermissionGate>
      );

      expect(screen.queryByText('Catalog Editor')).not.toBeInTheDocument();
    });
  });

  describe('no checks specified', () => {
    it('should render children when no checks are specified', () => {
      render(
        <PermissionGate>
          <span>Always visible</span>
        </PermissionGate>
      );

      expect(screen.getByText('Always visible')).toBeInTheDocument();
    });
  });

  describe('withPermission HOC', () => {
    it('should wrap component with PermissionGate', () => {
      mockAuth.hasRole.mockReturnValue(true);

      function MyComponent() {
        return <span>Protected Content</span>;
      }

      const ProtectedComponent = withPermission(MyComponent, { role: 'cpi-admin' });
      render(<ProtectedComponent />);

      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });

    it('should hide component when permission denied', () => {
      mockAuth.hasRole.mockReturnValue(false);

      function MyComponent() {
        return <span>Protected Content</span>;
      }

      const ProtectedComponent = withPermission(MyComponent, { role: 'cpi-admin' });
      render(<ProtectedComponent />);

      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });
  });
});
