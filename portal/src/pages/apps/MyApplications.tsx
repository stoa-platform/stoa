/**
 * My Applications Page
 *
 * Lists user's consumer applications with ability to create new ones.
 */

import { useState } from 'react';
import { Plus, AppWindow, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useApplications, useCreateApplication } from '../../hooks/useApplications';
import { ApplicationCard } from '../../components/apps/ApplicationCard';
import { CreateAppModal } from '../../components/apps/CreateAppModal';
import { CredentialsViewer } from '../../components/apps/CredentialsViewer';
import type { Application, ApplicationCreateRequest } from '../../types';

export function MyApplications() {
  const { t } = useTranslation('apps');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newlyCreatedApp, setNewlyCreatedApp] = useState<Application | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const { data: applications, isLoading, isError, error, refetch } = useApplications();

  const createMutation = useCreateApplication();

  const handleCreateApp = async (data: ApplicationCreateRequest) => {
    setCreateError(null);
    try {
      const newApp = await createMutation.mutateAsync(data);
      setNewlyCreatedApp(newApp);
      setIsCreateModalOpen(false);
    } catch (err) {
      setCreateError((err as Error)?.message || t('error.createFailed'));
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
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">{t('title')}</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">{t('subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="p-2 text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
            title={t('refresh')}
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            {t('createApp')}
          </button>
        </div>
      </div>

      {/* Newly created app credentials */}
      {newlyCreatedApp && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-green-900 dark:text-green-400">
                {t('created.title')}
              </h2>
              <p className="text-sm text-green-700 dark:text-green-400 mt-1">
                {t('created.subtitle', { name: newlyCreatedApp.name })}
              </p>
            </div>
            <button
              onClick={handleCloseCredentials}
              className="text-sm text-green-700 dark:text-green-400 hover:text-green-900 dark:hover:text-green-300 font-medium"
            >
              {t('created.dismiss')}
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
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-neutral-500 dark:text-neutral-400">{t('loading')}</p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800 dark:text-red-400">
                {t('error.loadFailed')}
              </h3>
              <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                {(error as Error)?.message || t('error.unexpected')}
              </p>
              <button
                onClick={() => refetch()}
                className="mt-3 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                {t('error.tryAgain')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && (!applications || applications.items.length === 0) && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
          <div className="inline-flex p-4 bg-neutral-100 dark:bg-neutral-700 rounded-full mb-4">
            <AppWindow className="h-8 w-8 text-neutral-400 dark:text-neutral-500" />
          </div>
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
            {t('empty.title')}
          </h2>
          <p className="text-neutral-500 dark:text-neutral-400 max-w-md mx-auto mb-6">
            {t('empty.description')}
          </p>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            {t('empty.createFirst')}
          </button>
        </div>
      )}

      {/* Applications grid */}
      {!isLoading && !isError && applications && applications.items.length > 0 && (
        <>
          <div className="text-sm text-neutral-500 dark:text-neutral-400">
            {t('count', { count: applications.items.length })}
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
