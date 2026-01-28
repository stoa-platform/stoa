// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * My Applications Page
 *
 * Lists user's consumer applications with ability to create new ones.
 */

import { useState } from 'react';
import { Plus, AppWindow, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { useApplications, useCreateApplication } from '../../hooks/useApplications';
import { ApplicationCard } from '../../components/apps/ApplicationCard';
import { CreateAppModal } from '../../components/apps/CreateAppModal';
import { CredentialsViewer } from '../../components/apps/CredentialsViewer';
import type { Application, ApplicationCreateRequest } from '../../types';

export function MyApplications() {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newlyCreatedApp, setNewlyCreatedApp] = useState<Application | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const {
    data: applications,
    isLoading,
    isError,
    error,
    refetch,
  } = useApplications();

  const createMutation = useCreateApplication();

  const handleCreateApp = async (data: ApplicationCreateRequest) => {
    setCreateError(null);
    try {
      const newApp = await createMutation.mutateAsync(data);
      setNewlyCreatedApp(newApp);
      setIsCreateModalOpen(false);
    } catch (err) {
      setCreateError((err as Error)?.message || 'Failed to create application');
    }
  };

  const handleCloseCredentials = () => {
    setNewlyCreatedApp(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Applications</h1>
          <p className="text-gray-500 mt-1">
            Manage your API consumer applications
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Create Application
          </button>
        </div>
      </div>

      {/* Newly created app credentials */}
      {newlyCreatedApp && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-green-900">
                Application Created Successfully!
              </h2>
              <p className="text-sm text-green-700 mt-1">
                Your application "{newlyCreatedApp.name}" has been created.
              </p>
            </div>
            <button
              onClick={handleCloseCredentials}
              className="text-sm text-green-700 hover:text-green-900 font-medium"
            >
              Dismiss
            </button>
          </div>
          <CredentialsViewer
            clientId={newlyCreatedApp.clientId}
            clientSecret={newlyCreatedApp.clientSecret}
            showSecretOnce={true}
          />
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading applications...</p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Failed to load applications</h3>
              <p className="text-sm text-red-600 mt-1">
                {(error as Error)?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => refetch()}
                className="mt-3 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && (!applications || applications.items.length === 0) && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
            <AppWindow className="h-8 w-8 text-gray-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">No Applications Yet</h2>
          <p className="text-gray-500 max-w-md mx-auto mb-6">
            Create your first application to start using APIs. Each application gets
            its own credentials for authentication.
          </p>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Create Your First Application
          </button>
        </div>
      )}

      {/* Applications grid */}
      {!isLoading && !isError && applications && applications.items.length > 0 && (
        <>
          <div className="text-sm text-gray-500">
            {applications.items.length === 1
              ? '1 application'
              : `${applications.items.length} applications`}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {applications.items.map((app: Application) => (
              <ApplicationCard key={app.id} application={app} />
            ))}
          </div>
        </>
      )}

      {/* Create Modal */}
      <CreateAppModal
        isOpen={isCreateModalOpen}
        onClose={() => {
          setIsCreateModalOpen(false);
          setCreateError(null);
        }}
        onSubmit={handleCreateApp}
        isLoading={createMutation.isPending}
        error={createError}
      />
    </div>
  );
}

export default MyApplications;
