/**
 * Consumer Detail Page
 *
 * Displays and manages a single external API consumer (CAB-1121).
 */

import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Users,
  Loader2,
  AlertCircle,
  CheckCircle,
  PauseCircle,
  ShieldOff,
  Clock,
  Mail,
  Building2,
  Hash,
  Key,
  Play,
  Pause,
  Ban,
  Trash2,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import {
  useConsumer,
  useDeleteConsumer,
  useSuspendConsumer,
  useActivateConsumer,
  useBlockConsumer,
} from '../../hooks/useConsumers';
import { CredentialsDisplay } from '../../components/consumers/CredentialsDisplay';
import type { ConsumerCredentials } from '../../types';

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
};

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export function ConsumerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const tenantId = user?.tenant_id || '';

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [credentials, setCredentials] = useState<ConsumerCredentials | null>(null);

  const { data: consumer, isLoading, isError, error } = useConsumer(tenantId || undefined, id);

  const deleteMutation = useDeleteConsumer(tenantId);
  const suspendMutation = useSuspendConsumer(tenantId);
  const activateMutation = useActivateConsumer(tenantId);
  const blockMutation = useBlockConsumer(tenantId);

  const handleDelete = async () => {
    if (id) {
      await deleteMutation.mutateAsync(id);
      navigate('/workspace?tab=consumers');
    }
  };

  const handleSuspend = async () => {
    if (id) await suspendMutation.mutateAsync(id);
  };

  const handleActivate = async () => {
    if (id) {
      const result = await activateMutation.mutateAsync(id);
      // If the activation returns credentials, display them
      if (result.keycloak_client_id) {
        // Credentials would come from the credentials endpoint
        // For now, we show that the consumer is activated
      }
    }
  };

  const handleBlock = async () => {
    if (id) await blockMutation.mutateAsync(id);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500 dark:text-neutral-400">Loading consumer...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (isError || !consumer) {
    return (
      <div className="space-y-6">
        <Link
          to="/workspace?tab=consumers"
          className="inline-flex items-center text-sm text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to Consumers
        </Link>

        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800 dark:text-red-300">
                Failed to load consumer
              </h3>
              <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                {(error as Error)?.message || 'The consumer could not be found.'}
              </p>
              <Link
                to="/workspace?tab=consumers"
                className="mt-3 inline-block px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50 text-sm font-medium transition-colors"
              >
                Return to Consumers
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const status = statusConfig[consumer.status] || statusConfig.active;
  const StatusIcon = status.icon;
  const isActionPending =
    suspendMutation.isPending ||
    activateMutation.isPending ||
    blockMutation.isPending ||
    deleteMutation.isPending;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/workspace?tab=consumers"
        className="inline-flex items-center text-sm text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-white"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Consumers
      </Link>

      {/* Header */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{consumer.name}</h1>
              <span
                className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${status.bg} ${status.text}`}
              >
                <StatusIcon className={`h-3 w-3 ${status.color}`} />
                {status.label}
              </span>
            </div>
            <p className="text-gray-600 dark:text-neutral-300">
              {consumer.description || 'No description provided'}
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {consumer.status === 'suspended' && (
              <button
                onClick={handleActivate}
                disabled={isActionPending}
                className="inline-flex items-center gap-2 px-4 py-2 border border-green-300 dark:border-green-700 text-green-700 dark:text-green-400 rounded-lg hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors disabled:opacity-50"
              >
                <Play className="h-4 w-4" />
                Activate
              </button>
            )}
            {consumer.status === 'active' && (
              <button
                onClick={handleSuspend}
                disabled={isActionPending}
                className="inline-flex items-center gap-2 px-4 py-2 border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors disabled:opacity-50"
              >
                <Pause className="h-4 w-4" />
                Suspend
              </button>
            )}
            {consumer.status !== 'blocked' && (
              <button
                onClick={handleBlock}
                disabled={isActionPending}
                className="inline-flex items-center gap-2 px-4 py-2 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
              >
                <Ban className="h-4 w-4" />
                Block
              </button>
            )}
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isActionPending}
              className="inline-flex items-center gap-2 px-4 py-2 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          </div>
        </div>

        {/* Metadata */}
        <div className="flex flex-wrap items-center gap-6 mt-6 pt-6 border-t border-gray-100 dark:border-neutral-700 text-sm text-gray-500 dark:text-neutral-400">
          <div className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            Created {formatDate(consumer.created_at)}
          </div>
          {consumer.updated_at !== consumer.created_at && (
            <div>Updated {formatDate(consumer.updated_at)}</div>
          )}
        </div>
      </div>

      {/* Details */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Consumer Details
        </h3>
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <dt className="text-sm font-medium text-gray-500 dark:text-neutral-400 flex items-center gap-1">
              <Hash className="h-3.5 w-3.5" /> External ID
            </dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white font-mono">
              {consumer.external_id}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500 dark:text-neutral-400 flex items-center gap-1">
              <Mail className="h-3.5 w-3.5" /> Email
            </dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white">{consumer.email}</dd>
          </div>
          {consumer.company && (
            <div>
              <dt className="text-sm font-medium text-gray-500 dark:text-neutral-400 flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5" /> Company
              </dt>
              <dd className="mt-1 text-sm text-gray-900 dark:text-white">{consumer.company}</dd>
            </div>
          )}
          {consumer.keycloak_client_id && (
            <div>
              <dt className="text-sm font-medium text-gray-500 dark:text-neutral-400 flex items-center gap-1">
                <Key className="h-3.5 w-3.5" /> OAuth Client ID
              </dt>
              <dd className="mt-1 text-sm text-gray-900 dark:text-white font-mono">
                {consumer.keycloak_client_id}
              </dd>
            </div>
          )}
          <div className="md:col-span-2">
            <dt className="text-sm font-medium text-gray-500 dark:text-neutral-400 flex items-center gap-1">
              <Users className="h-3.5 w-3.5" /> Description
            </dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white">
              {consumer.description || 'No description provided'}
            </dd>
          </div>
        </dl>
      </div>

      {/* Credentials (if available) */}
      {credentials && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            OAuth Credentials
          </h3>
          <CredentialsDisplay credentials={credentials} />
          <button
            onClick={() => setCredentials(null)}
            className="mt-4 text-sm text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200"
          >
            Dismiss credentials
          </button>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setShowDeleteConfirm(false)}
            onKeyDown={(e) => e.key === 'Escape' && setShowDeleteConfirm(false)}
            role="button"
            aria-label="Close modal"
            tabIndex={0}
          />
          <div className="flex min-h-full items-center justify-center p-4">
            <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-md w-full p-6">
              <div className="flex items-start gap-4">
                <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-full">
                  <Trash2 className="h-6 w-6 text-red-600 dark:text-red-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Delete Consumer
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-neutral-300 mt-2">
                    Are you sure you want to delete &quot;{consumer.name}&quot;? This action cannot
                    be undone and will revoke all OAuth credentials.
                  </p>
                </div>
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleteMutation.isPending}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
                >
                  {deleteMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    'Delete Consumer'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ConsumerDetailPage;
