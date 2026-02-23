import { useSearchParams } from 'react-router-dom';
import { Suspense, lazy, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { AppWindow, CreditCard, FileCode2, ShieldCheck } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { config } from '../../config';
import { loadNamespace } from '../../i18n';

const MyApplications = lazy(() => import('../apps').then((m) => ({ default: m.MyApplications })));
const MySubscriptions = lazy(() =>
  import('../subscriptions/MySubscriptions').then((m) => ({ default: m.MySubscriptions }))
);
const ContractListPage = lazy(() =>
  import('../contracts').then((m) => ({ default: m.ContractListPage }))
);
const ApprovalQueue = lazy(() =>
  import('../../components/consumers/ApprovalQueue').then((m) => ({ default: m.ApprovalQueue }))
);

const allTabs = [
  { id: 'apps', label: 'Apps', icon: AppWindow, adminOnly: false },
  { id: 'subscriptions', label: 'Subscriptions', icon: CreditCard, adminOnly: false },
  { id: 'contracts', label: 'Contracts', icon: FileCode2, adminOnly: false },
  { id: 'approvals', label: 'Approvals', icon: ShieldCheck, adminOnly: true },
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
  const { hasRole } = useAuth();
  const { t, i18n: i18nInstance } = useTranslation('workspace');
  const i18nEnabled = config.features.enableI18n;

  useEffect(() => {
    if (i18nEnabled) {
      const lng = i18nInstance.language;
      loadNamespace(lng, 'workspace');
      if (lng !== 'en') loadNamespace('en', 'workspace');
    }
  }, [i18nEnabled, i18nInstance.language]);
  const activeTab = (searchParams.get('tab') as TabId) || 'apps';

  const isAdmin = hasRole('tenant-admin') || hasRole('cpi-admin');
  const tabs = allTabs.filter((tab) => !tab.adminOnly || isAdmin);

  const setTab = (tab: TabId) => {
    setSearchParams({ tab }, { replace: true });
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
          {i18nEnabled ? t('title') : 'My Workspace'}
        </h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          {i18nEnabled ? t('subtitle') : 'Manage your apps, subscriptions, and contracts'}
        </p>
      </div>

      {/* Tab bar */}
      <div className="border-b border-neutral-200 dark:border-neutral-700 mb-6">
        <nav className="-mb-px flex gap-6" aria-label="Workspace tabs">
          {tabs.map((tab) => {
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
                {i18nEnabled ? t(`tabs.${tab.id}`) : tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      <Suspense fallback={<TabSkeleton />}>
        {activeTab === 'apps' && <MyApplications />}
        {activeTab === 'subscriptions' && <MySubscriptions />}
        {activeTab === 'contracts' && <ContractListPage />}
        {activeTab === 'approvals' && <ApprovalQueue />}
      </Suspense>
    </div>
  );
}
