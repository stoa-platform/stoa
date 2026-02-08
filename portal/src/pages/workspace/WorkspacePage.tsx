import { useSearchParams } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { AppWindow, CreditCard, FileCode2 } from 'lucide-react';

const MyApplications = lazy(() => import('../apps').then((m) => ({ default: m.MyApplications })));
const MySubscriptions = lazy(() =>
  import('../subscriptions/MySubscriptions').then((m) => ({ default: m.MySubscriptions }))
);
const ContractListPage = lazy(() =>
  import('../contracts').then((m) => ({ default: m.ContractListPage }))
);

const tabs = [
  { id: 'apps', label: 'Apps', icon: AppWindow },
  { id: 'subscriptions', label: 'Subscriptions', icon: CreditCard },
  { id: 'contracts', label: 'Contracts', icon: FileCode2 },
] as const;

type TabId = (typeof tabs)[number]['id'];

function TabSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-8 bg-gray-200 dark:bg-neutral-700 rounded w-1/3" />
      <div className="h-4 bg-gray-200 dark:bg-neutral-700 rounded w-2/3" />
      <div className="h-64 bg-gray-200 dark:bg-neutral-700 rounded" />
    </div>
  );
}

export function WorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') as TabId) || 'apps';

  const setTab = (tab: TabId) => {
    setSearchParams({ tab }, { replace: true });
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Workspace</h1>
        <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
          Manage your apps, subscriptions, and contracts
        </p>
      </div>

      {/* Tab bar */}
      <div className="border-b border-gray-200 dark:border-neutral-700 mb-6">
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
                    : 'border-transparent text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 hover:border-gray-300 dark:hover:border-neutral-600'
                }`}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
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
      </Suspense>
    </div>
  );
}
