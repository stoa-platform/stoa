/**
 * Unified APIs page — 3 tabs: Catalog | Backend APIs | Platform Backends
 *
 * Follows the same tab pattern as MCPServersUnified.
 * - Catalog: existing APIs page (tenant API lifecycle)
 * - Backend APIs: tenant-scoped backend registrations (CAB-1251)
 * - Platform Backends: platform-level proxy backends, admin only (CAB-1727)
 */

import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Layers, Server, Shield } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { APIs } from './APIs';
import { BackendApisList } from './BackendApis';
import { InternalApisList } from './InternalApis';

type TabId = 'catalog' | 'backends' | 'platform';

interface TabConfig {
  id: TabId;
  label: string;
  icon: typeof Layers;
  permission?: string;
}

const tabs: TabConfig[] = [
  { id: 'catalog', label: 'API Catalog', icon: Layers },
  { id: 'backends', label: 'Backend APIs', icon: Server, permission: 'apis:read' },
  { id: 'platform', label: 'Platform Backends', icon: Shield, permission: 'tenants:read' },
];

export function APIsUnified() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { hasPermission } = useAuth();
  const activeTab = (searchParams.get('tab') as TabId) || 'catalog';

  const setActiveTab = useCallback(
    (tab: TabId) => setSearchParams({ tab }, { replace: true }),
    [setSearchParams]
  );

  const visibleTabs = tabs.filter((t) => !t.permission || hasPermission(t.permission));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">APIs</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          Manage API catalog, backend registrations, and platform proxy backends
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-neutral-200 dark:border-neutral-700">
        <nav className="-mb-px flex gap-6" aria-label="Tabs">
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`whitespace-nowrap pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                  : 'border-transparent text-neutral-500 hover:text-neutral-700 hover:border-neutral-300 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <tab.icon className="inline h-4 w-4 mr-1.5 -mt-0.5" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'catalog' && <APIs />}
      {activeTab === 'backends' && <BackendApisList />}
      {activeTab === 'platform' && <InternalApisList />}
    </div>
  );
}
