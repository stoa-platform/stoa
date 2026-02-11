import { useMemo } from 'react';
import { useEnvironment } from '../contexts/EnvironmentContext';
import { useAuth } from '../contexts/AuthContext';

export interface EnvironmentPermissions {
  canCreate: boolean;
  canEdit: boolean;
  canDelete: boolean;
  canDeploy: boolean;
  isReadOnly: boolean;
}

/**
 * Returns write permissions based on the active environment mode.
 * - `full` mode: all writes allowed
 * - `read-only` mode: writes blocked (unless cpi-admin override)
 * - `promote-only` mode: only deploy/promote allowed
 */
export function useEnvironmentMode(): EnvironmentPermissions {
  const { activeConfig } = useEnvironment();
  const { hasRole } = useAuth();

  return useMemo(() => {
    const mode = activeConfig.mode;
    const isAdmin = hasRole('cpi-admin');

    if (mode === 'full') {
      return {
        canCreate: true,
        canEdit: true,
        canDelete: true,
        canDeploy: true,
        isReadOnly: false,
      };
    }

    if (mode === 'read-only') {
      // cpi-admin can override read-only for emergency hotfixes
      if (isAdmin) {
        return {
          canCreate: true,
          canEdit: true,
          canDelete: true,
          canDeploy: true,
          isReadOnly: false,
        };
      }
      return {
        canCreate: false,
        canEdit: false,
        canDelete: false,
        canDeploy: false,
        isReadOnly: true,
      };
    }

    // promote-only: can deploy but not create/edit/delete
    return {
      canCreate: false,
      canEdit: false,
      canDelete: false,
      canDeploy: true,
      isReadOnly: false,
    };
  }, [activeConfig.mode, hasRole]);
}
