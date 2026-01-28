// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Application Card Component
 *
 * Displays a consumer application in the applications list.
 * Optimized with React.memo to prevent unnecessary re-renders.
 */

import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Key, Clock, CheckCircle, XCircle, PauseCircle } from 'lucide-react';
import type { Application } from '../../types';

interface ApplicationCardProps {
  application: Application;
}

// Move static config outside component
const statusConfig = {
  active: {
    icon: CheckCircle,
    color: 'text-green-500',
    bg: 'bg-green-100',
    text: 'text-green-800',
    label: 'Active',
  },
  suspended: {
    icon: PauseCircle,
    color: 'text-amber-500',
    bg: 'bg-amber-100',
    text: 'text-amber-800',
    label: 'Suspended',
  },
  deleted: {
    icon: XCircle,
    color: 'text-red-500',
    bg: 'bg-red-100',
    text: 'text-red-800',
    label: 'Deleted',
  },
} as const;

// Date formatting options - created once
const dateFormatOptions: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
};

export const ApplicationCard = memo(function ApplicationCard({ application }: ApplicationCardProps) {
  const status = statusConfig[application.status] || statusConfig.active;
  const StatusIcon = status.icon;

  // Memoize formatted date
  const formattedDate = useMemo(() => {
    return new Date(application.createdAt).toLocaleDateString('en-US', dateFormatOptions);
  }, [application.createdAt]);

  const subscriptionCount = application.subscriptions?.length || 0;

  return (
    <Link
      to={`/apps/${application.id}`}
      className="group bg-white rounded-lg border border-gray-200 p-6 hover:border-primary-300 hover:shadow-md transition-all"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 group-hover:text-primary-700 transition-colors truncate">
            {application.name}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            <Key className="h-3 w-3 text-gray-400" />
            <span className="text-xs font-mono text-gray-500 truncate">
              {application.clientId}
            </span>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${status.bg} ${status.text}`}>
          <StatusIcon className={`h-3 w-3 ${status.color}`} />
          {status.label}
        </span>
      </div>

      <p className="text-sm text-gray-600 line-clamp-2 mb-4 min-h-[40px]">
        {application.description || 'No description provided'}
      </p>

      <div className="flex flex-wrap gap-3 mb-4">
        <div className="text-sm">
          <span className="text-gray-500">Subscriptions:</span>{' '}
          <span className="font-medium text-gray-900">{subscriptionCount}</span>
        </div>
        {application.callbackUrls && application.callbackUrls.length > 0 && (
          <div className="text-sm">
            <span className="text-gray-500">Callbacks:</span>{' '}
            <span className="font-medium text-gray-900">{application.callbackUrls.length}</span>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <div className="flex items-center text-xs text-gray-500">
          <Clock className="h-3 w-3 mr-1" />
          Created {formattedDate}
        </div>
        <span className="inline-flex items-center text-sm font-medium text-primary-600 group-hover:text-primary-700">
          Manage
          <ArrowRight className="h-4 w-4 ml-1 group-hover:translate-x-1 transition-transform" />
        </span>
      </div>
    </Link>
  );
});

export default ApplicationCard;
