import { useSearchParams } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
import { AppWindow, CreditCard, BarChart3, History } from 'lucide-react';

const MyApplications = lazy(() => import('../apps').then((m) => ({ default: m.MyApplications })));
const MySubscriptions = lazy(() =>
  import('../subscriptions/MySubscriptions').then((m) => ({ default: m.MySubscriptions }))
);
const UsagePage = lazy(() => import('../usage').then((m) => ({ default: m.UsagePage })));
const ExecutionHistoryPage = lazy(() =>
  import('../executions').then((m) => ({ default: m.ExecutionHistoryPage }))
);

const allTabs = [
  { id: 'apps', label: 'Apps', icon: AppWindow },
  { id: 'subscriptions', label: 'Subscriptions', icon: CreditCard },
  { id: 'usage', label: 'Usage', icon: BarChart3 },
  { id: 'executions', label: 'Executions', icon: History },
] as const;

type TabId = (typeof allTabs)[number]['id'];

function TabSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-8 bg-neutral-200 dark:bg-neutral-700 rounded w-1/3" />
      <div className="h-4 bg-neutral-200 dark:bg-neutral-700 rounded w-2/3" />
      <div className="h-64 bg-neutral-200 dark:bg-neutral-700 rounded" />
    </div>
  );
}

export function WorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { t } = useTranslation('workspace');
  const activeTab = (searchParams.get('tab') as TabId) || 'apps';

  const setTab = (tab: TabId) => {
    setSearchParams({ tab }, { replace: true });
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
          {t('title', { defaultValue: 'My Workspace' })}
        </h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          {t('subtitle', { defaultValue: 'Manage your apps and subscriptions' })}
        </p>
      </div>

      {/* Tab bar */}
      <div className="border-b border-neutral-200 dark:border-neutral-700 mb-6">
        <nav className="-mb-px flex gap-6" aria-label="Workspace tabs">
          {allTabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setTab(tab.id)}
                className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                    : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:border-neutral-300 dark:hover:border-neutral-600'
                }`}
              >
                <tab.icon className="h-4 w-4" />
                {t(`tabs.${tab.id}`, { defaultValue: tab.label })}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      <Suspense fallback={<TabSkeleton />}>
        {activeTab === 'apps' && <MyApplications />}
        {activeTab === 'subscriptions' && <MySubscriptions />}
        {activeTab === 'usage' && <UsagePage />}
        {activeTab === 'executions' && <ExecutionHistoryPage />}
      </Suspense>
    </div>
  );
}
