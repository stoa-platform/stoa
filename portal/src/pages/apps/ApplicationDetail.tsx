/**
 * Application Detail Page
 *
 * Displays and manages a single consumer application.
 */

import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  AppWindow,
  Settings,
  CreditCard,
  Trash2,
  Loader2,
  AlertCircle,
  CheckCircle,
  PauseCircle,
  XCircle,
  ExternalLink,
  Clock,
} from 'lucide-react';
import {
  useApplication,
  useDeleteApplication,
  useRegenerateSecret,
} from '../../hooks/useApplications';
import { useApplicationSubscriptions } from '../../hooks/useSubscriptions';
import { CredentialsViewer } from '../../components/apps/CredentialsViewer';
import type { APISubscription } from '../../types';

type TabType = 'overview' | 'credentials' | 'subscriptions';

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  const { data: application, isLoading, isError, error } = useApplication(id);
  const { data: subscriptions, isLoading: subscriptionsLoading } = useApplicationSubscriptions(id);
  const deleteMutation = useDeleteApplication();
  const regenerateMutation = useRegenerateSecret(id || '');

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

  const handleDelete = async () => {
    if (id) {
      await deleteMutation.mutateAsync(id);
      navigate('/apps');
    }
  };

  const handleRegenerateSecret = async (): Promise<string | undefined> => {
    if (id) {
      const result = await regenerateMutation.mutateAsync();
      if (result.clientSecret) {
        setNewSecret(result.clientSecret);
        return result.clientSecret;
      }
    }
    return undefined;
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading application...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (isError || !application) {
    return (
      <div className="space-y-6">
        <Link
          to="/apps"
          className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to Applications
        </Link>

        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Failed to load application</h3>
              <p className="text-sm text-red-600 mt-1">
                {(error as Error)?.message || 'The application could not be found.'}
              </p>
              <Link
                to="/apps"
                className="mt-3 inline-block px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                Return to Applications
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const status = statusConfig[application.status] || statusConfig.active;
  const StatusIcon = status.icon;

  const tabs: { id: TabType; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'overview', label: 'Overview', icon: AppWindow },
    { id: 'credentials', label: 'Credentials', icon: Settings },
    { id: 'subscriptions', label: 'Subscriptions', icon: CreditCard },
  ];

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/apps"
        className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Applications
      </Link>

      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900">{application.name}</h1>
              <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${status.bg} ${status.text}`}>
                <StatusIcon className={`h-3 w-3 ${status.color}`} />
                {status.label}
              </span>
            </div>
            <p className="text-gray-600">
              {application.description || 'No description provided'}
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={application.status === 'deleted'}
              className="inline-flex items-center gap-2 px-4 py-2 border border-red-300 text-red-700 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          </div>
        </div>

        {/* Metadata */}
        <div className="flex items-center gap-6 mt-6 pt-6 border-t border-gray-100 text-sm text-gray-500">
          <div className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            Created {formatDate(application.createdAt)}
          </div>
          {application.updatedAt !== application.createdAt && (
            <div>
              Updated {formatDate(application.updatedAt)}
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 py-3 border-b-2 text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
                {tab.id === 'subscriptions' && subscriptions && (
                  <span className="ml-1 px-2 py-0.5 text-xs bg-gray-100 rounded-full">
                    {subscriptions.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-lg border border-gray-200">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="p-6 space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Application Details</h3>
              <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <dt className="text-sm font-medium text-gray-500">Client ID</dt>
                  <dd className="mt-1 text-sm text-gray-900 font-mono">{application.clientId}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500">Status</dt>
                  <dd className="mt-1">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${status.bg} ${status.text}`}>
                      <StatusIcon className={`h-3 w-3 ${status.color}`} />
                      {status.label}
                    </span>
                  </dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-sm font-medium text-gray-500">Description</dt>
                  <dd className="mt-1 text-sm text-gray-900">
                    {application.description || 'No description provided'}
                  </dd>
                </div>
              </dl>
            </div>

            {/* Callback URLs */}
            {application.callbackUrls && application.callbackUrls.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Callback URLs</h3>
                <ul className="space-y-2">
                  {application.callbackUrls.map((url, index) => (
                    <li key={index} className="flex items-center gap-2 text-sm">
                      <ExternalLink className="h-4 w-4 text-gray-400" />
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-600 hover:text-primary-700 hover:underline font-mono"
                      >
                        {url}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Credentials Tab */}
        {activeTab === 'credentials' && (
          <div className="p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">API Credentials</h3>
            <p className="text-sm text-gray-600 mb-6">
              Use these credentials to authenticate your application with our APIs.
            </p>
            <CredentialsViewer
              clientId={application.clientId}
              clientSecret={newSecret}
              onRegenerateSecret={handleRegenerateSecret}
              isRegenerating={regenerateMutation.isPending}
            />
          </div>
        )}

        {/* Subscriptions Tab */}
        {activeTab === 'subscriptions' && (
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">API Subscriptions</h3>
                <p className="text-sm text-gray-600 mt-1">
                  APIs this application is subscribed to
                </p>
              </div>
              <Link
                to="/apis"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm"
              >
                Browse APIs
              </Link>
            </div>

            {subscriptionsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 text-primary-600 animate-spin" />
              </div>
            ) : subscriptions && subscriptions.length > 0 ? (
              <div className="divide-y divide-gray-200">
                {subscriptions.map((sub: APISubscription) => (
                  <div key={sub.id} className="py-4 flex items-center justify-between">
                    <div>
                      <Link
                        to={`/apis/${sub.apiId}`}
                        className="font-medium text-gray-900 hover:text-primary-600"
                      >
                        {sub.api?.name || sub.apiId}
                      </Link>
                      <p className="text-sm text-gray-500 mt-1">
                        Subscribed on {formatDate(sub.createdAt)}
                      </p>
                    </div>
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                      sub.status === 'active' ? 'bg-green-100 text-green-800' :
                      sub.status === 'pending' ? 'bg-amber-100 text-amber-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {sub.status}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <CreditCard className="h-8 w-8 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500">No subscriptions yet</p>
                <p className="text-sm text-gray-400 mt-1">
                  Browse the API catalog to subscribe to APIs
                </p>
              </div>
            )}
          </div>
        )}
      </div>

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
            <div className="relative bg-white rounded-xl shadow-xl max-w-md w-full p-6">
              <div className="flex items-start gap-4">
                <div className="p-3 bg-red-100 rounded-full">
                  <Trash2 className="h-6 w-6 text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Delete Application</h3>
                  <p className="text-sm text-gray-600 mt-2">
                    Are you sure you want to delete "{application.name}"? This action cannot be
                    undone and will revoke all credentials.
                  </p>
                </div>
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleteMutation.isPending}
                  className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
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
                    'Delete Application'
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

export default ApplicationDetail;
