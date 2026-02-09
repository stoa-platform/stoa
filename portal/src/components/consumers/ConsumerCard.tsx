/**
 * Consumer Card Component
 *
 * Displays an external API consumer in the consumers list.
 * Optimized with React.memo to prevent unnecessary re-renders.
 */

import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Clock,
  CheckCircle,
  PauseCircle,
  ShieldOff,
  Mail,
  Building2,
  Hash,
} from 'lucide-react';
import type { Consumer } from '../../types';

interface ConsumerCardProps {
  consumer: Consumer;
}

const statusConfig = {
  active: {
    icon: CheckCircle,
    color: 'text-green-500',
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-300',
    label: 'Active',
  },
  suspended: {
    icon: PauseCircle,
    color: 'text-amber-500',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-800 dark:text-amber-300',
    label: 'Suspended',
  },
  blocked: {
    icon: ShieldOff,
    color: 'text-red-500',
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-300',
    label: 'Blocked',
  },
} as const;

const dateFormatOptions: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
};

export const ConsumerCard = memo(function ConsumerCard({ consumer }: ConsumerCardProps) {
  const status = statusConfig[consumer.status] || statusConfig.active;
  const StatusIcon = status.icon;

  const formattedDate = useMemo(() => {
    return new Date(consumer.created_at).toLocaleDateString('en-US', dateFormatOptions);
  }, [consumer.created_at]);

  return (
    <Link
      to={`/consumers/${consumer.id}`}
      className="group bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-6 hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-md transition-all"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 dark:text-white group-hover:text-primary-700 dark:group-hover:text-primary-400 transition-colors truncate">
            {consumer.name}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            <Hash className="h-3 w-3 text-gray-400 dark:text-neutral-500" />
            <span className="text-xs font-mono text-gray-500 dark:text-neutral-400 truncate">
              {consumer.external_id}
            </span>
          </div>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${status.bg} ${status.text}`}
        >
          <StatusIcon className={`h-3 w-3 ${status.color}`} />
          {status.label}
        </span>
      </div>

      <p className="text-sm text-gray-600 dark:text-neutral-300 line-clamp-2 mb-4 min-h-[40px]">
        {consumer.description || 'No description provided'}
      </p>

      <div className="flex flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-neutral-400">
          <Mail className="h-3.5 w-3.5" />
          <span className="truncate max-w-[180px]">{consumer.email}</span>
        </div>
        {consumer.company && (
          <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-neutral-400">
            <Building2 className="h-3.5 w-3.5" />
            <span className="truncate max-w-[120px]">{consumer.company}</span>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-neutral-700">
        <div className="flex items-center text-xs text-gray-500 dark:text-neutral-400">
          <Clock className="h-3 w-3 mr-1" />
          Created {formattedDate}
        </div>
        <span className="inline-flex items-center text-sm font-medium text-primary-600 dark:text-primary-400 group-hover:text-primary-700 dark:group-hover:text-primary-300">
          View
          <ArrowRight className="h-4 w-4 ml-1 group-hover:translate-x-1 transition-transform" />
        </span>
      </div>
    </Link>
  );
});

export default ConsumerCard;
