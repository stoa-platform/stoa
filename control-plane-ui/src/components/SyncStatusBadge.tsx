import { clsx } from 'clsx';
import type { DeploymentSyncStatus } from '../types';

const statusConfig: Record<DeploymentSyncStatus, { label: string; classes: string }> = {
  pending: {
    label: 'Pending',
    classes: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  syncing: {
    label: 'Syncing',
    classes: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 animate-pulse',
  },
  synced: {
    label: 'Synced',
    classes: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  },
  drifted: {
    label: 'Drifted',
    classes: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  },
  error: {
    label: 'Error',
    classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  },
  deleting: {
    label: 'Deleting',
    classes: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-400',
  },
};

interface SyncStatusBadgeProps {
  status: DeploymentSyncStatus;
  className?: string;
}

export function SyncStatusBadge({ status, className }: SyncStatusBadgeProps) {
  const config = statusConfig[status] || {
    label: status,
    classes: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-400',
  };

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        config.classes,
        className
      )}
    >
      {config.label}
    </span>
  );
}
