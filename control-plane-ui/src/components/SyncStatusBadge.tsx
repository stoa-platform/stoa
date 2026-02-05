import { clsx } from 'clsx';
import type { DeploymentSyncStatus } from '../types';

const statusConfig: Record<DeploymentSyncStatus, { label: string; classes: string }> = {
  pending: { label: 'Pending', classes: 'bg-yellow-100 text-yellow-800' },
  syncing: { label: 'Syncing', classes: 'bg-blue-100 text-blue-800 animate-pulse' },
  synced: { label: 'Synced', classes: 'bg-green-100 text-green-800' },
  drifted: { label: 'Drifted', classes: 'bg-orange-100 text-orange-800' },
  error: { label: 'Error', classes: 'bg-red-100 text-red-800' },
  deleting: { label: 'Deleting', classes: 'bg-gray-100 text-gray-800' },
};

interface SyncStatusBadgeProps {
  status: DeploymentSyncStatus;
  className?: string;
}

export function SyncStatusBadge({ status, className }: SyncStatusBadgeProps) {
  const config = statusConfig[status] || { label: status, classes: 'bg-gray-100 text-gray-800' };

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
