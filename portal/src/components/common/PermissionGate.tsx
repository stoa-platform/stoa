// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * PermissionGate - Conditional rendering based on RBAC permissions
 *
 * Use this component to conditionally render UI elements based on user permissions.
 *
 * @example
 * // Single permission check
 * <PermissionGate permission="apis:create">
 *   <CreateAPIButton />
 * </PermissionGate>
 *
 * @example
 * // Multiple permissions (OR by default)
 * <PermissionGate permissions={['apis:create', 'apis:update']}>
 *   <EditAPIButton />
 * </PermissionGate>
 *
 * @example
 * // Multiple permissions with AND logic
 * <PermissionGate permissions={['apis:create', 'apis:deploy']} requireAll>
 *   <CreateAndDeployButton />
 * </PermissionGate>
 *
 * @example
 * // Role-based check
 * <PermissionGate role="cpi-admin">
 *   <AdminPanel />
 * </PermissionGate>
 *
 * @example
 * // Scope-based check
 * <PermissionGate scope="stoa:catalog:write">
 *   <CatalogEditor />
 * </PermissionGate>
 *
 * @example
 * // With fallback content
 * <PermissionGate permission="apis:delete" fallback={<DisabledButton />}>
 *   <DeleteButton />
 * </PermissionGate>
 */
import { ReactNode } from 'react';
import { useAuth } from '../../contexts/AuthContext';

interface PermissionGateProps {
  children: ReactNode;
  /** Single permission to check */
  permission?: string;
  /** Multiple permissions to check */
  permissions?: string[];
  /** If true, ALL permissions must be present. If false (default), ANY permission suffices */
  requireAll?: boolean;
  /** Role to check (Keycloak realm role) */
  role?: string;
  /** OAuth2 scope to check */
  scope?: string;
  /** Content to render if permission check fails */
  fallback?: ReactNode;
}

export function PermissionGate({
  children,
  permission,
  permissions,
  requireAll = false,
  role,
  scope,
  fallback = null,
}: PermissionGateProps) {
  const { hasPermission, hasAnyPermission, hasAllPermissions, hasRole, hasScope } = useAuth();

  // Check single permission
  if (permission && !hasPermission(permission)) {
    return <>{fallback}</>;
  }

  // Check multiple permissions
  if (permissions && permissions.length > 0) {
    const hasAccess = requireAll
      ? hasAllPermissions(permissions)
      : hasAnyPermission(permissions);
    if (!hasAccess) {
      return <>{fallback}</>;
    }
  }

  // Check role
  if (role && !hasRole(role)) {
    return <>{fallback}</>;
  }

  // Check scope
  if (scope && !hasScope(scope)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}

/**
 * Higher-order component version of PermissionGate
 *
 * @example
 * const AdminOnlyComponent = withPermission(MyComponent, { role: 'cpi-admin' });
 */
export function withPermission<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  gateProps: Omit<PermissionGateProps, 'children'>
) {
  return function PermissionGatedComponent(props: P) {
    return (
      <PermissionGate {...gateProps}>
        <WrappedComponent {...props} />
      </PermissionGate>
    );
  };
}

export default PermissionGate;
