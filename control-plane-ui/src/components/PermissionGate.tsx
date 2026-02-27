/**
 * PermissionGate — Widget-level RBAC wrapper (CAB-1545)
 *
 * Wraps any UI section to show/hide based on user permissions.
 * Supports both permission strings and role checks.
 *
 * Usage:
 *   <PermissionGate permission="tenants:read">
 *     <AdminWidget />
 *   </PermissionGate>
 *
 *   <PermissionGate role="cpi-admin" fallback={<UpgradePrompt />}>
 *     <PlatformSettings />
 *   </PermissionGate>
 */

import { type ReactNode } from 'react';
import { useAuth } from '../contexts/AuthContext';

interface PermissionGateProps {
  /** Required permission string (e.g. 'tenants:read') */
  permission?: string;
  /** Required role (e.g. 'cpi-admin') */
  role?: string;
  /** Content to render when authorized */
  children: ReactNode;
  /** Optional fallback when unauthorized (default: nothing) */
  fallback?: ReactNode;
}

export function PermissionGate({
  permission,
  role,
  children,
  fallback = null,
}: PermissionGateProps) {
  const { hasPermission, hasRole } = useAuth();

  const isAuthorized =
    (permission ? hasPermission(permission) : true) && (role ? hasRole(role) : true);

  if (!isAuthorized) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
