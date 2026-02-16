import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SyncStatusBadge } from './SyncStatusBadge';
import type { DeploymentSyncStatus } from '../types';

describe('SyncStatusBadge', () => {
  const statuses: Array<{ status: DeploymentSyncStatus; label: string; colorClass: string }> = [
    { status: 'pending', label: 'Pending', colorClass: 'bg-yellow-100' },
    { status: 'syncing', label: 'Syncing', colorClass: 'bg-blue-100' },
    { status: 'synced', label: 'Synced', colorClass: 'bg-green-100' },
    { status: 'drifted', label: 'Drifted', colorClass: 'bg-orange-100' },
    { status: 'error', label: 'Error', colorClass: 'bg-red-100' },
    { status: 'deleting', label: 'Deleting', colorClass: 'bg-gray-100' },
  ];

  it.each(statuses)('renders "$label" for status "$status"', ({ status, label }) => {
    render(<SyncStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it.each(statuses)('applies correct color class for "$status"', ({ status, colorClass }) => {
    const { container } = render(<SyncStatusBadge status={status} />);
    expect(container.firstChild).toHaveClass(colorClass);
  });

  it('applies syncing animation', () => {
    const { container } = render(<SyncStatusBadge status="syncing" />);
    expect(container.firstChild).toHaveClass('animate-pulse');
  });

  it('applies custom className', () => {
    const { container } = render(<SyncStatusBadge status="synced" className="mt-2" />);
    expect(container.firstChild).toHaveClass('mt-2');
  });

  it('falls back for unknown status', () => {
    render(<SyncStatusBadge status={'unknown' as DeploymentSyncStatus} />);
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });

  it('always has base badge classes', () => {
    const { container } = render(<SyncStatusBadge status="synced" />);
    expect(container.firstChild).toHaveClass('inline-flex', 'items-center', 'rounded-full');
  });
});
