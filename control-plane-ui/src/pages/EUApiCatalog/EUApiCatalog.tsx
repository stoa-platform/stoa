import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Globe,
  CheckCircle2,
  FlaskConical,
  Users,
  ExternalLink,
  X,
  Rocket,
  RefreshCw,
} from 'lucide-react';
import { discoveryService } from '../../services/discoveryApi';
import { backendApisService } from '../../services/backendApisApi';
import { useAuth } from '../../contexts/AuthContext';
import { useToastActions } from '@stoa/shared/components/Toast';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { BackendApiAuthType, CatalogEntry } from '../../types';

const statusConfig = {
  verified: {
    label: 'Verified',
    icon: CheckCircle2,
    className: 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300',
  },
  community: {
    label: 'Community',
    icon: Users,
    className: 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
  },
  experimental: {
    label: 'Experimental',
    icon: FlaskConical,
    className: 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
  },
};

/** Map catalog auth_type to BackendApiAuthType */
function toBackendAuthType(catalogAuth: string): BackendApiAuthType {
  if (catalogAuth === 'api_key') return 'api_key';
  if (catalogAuth === 'oauth2') return 'oauth2_cc';
  if (catalogAuth === 'basic') return 'basic';
  return 'none';
}

/** Derive a slug-safe API name from display_name */
function toSlug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 64);
}

const ALL = '__all__';

// ─── Main Page ────────────────────────────────────────────────────────────────

export function EUApiCatalog() {
  const { user } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();

  const [categoryFilter, setCategoryFilter] = useState(ALL);
  const [countryFilter, setCountryFilter] = useState(ALL);
  const [deployEntry, setDeployEntry] = useState<CatalogEntry | null>(null);
  const [deploying, setDeploying] = useState(false);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['eu-catalog'],
    queryFn: () => discoveryService.getCatalog(),
  });

  const entries = data?.entries ?? [];
  const categories = data?.categories ?? [];

  const countries = [ALL, ...Array.from(new Set(entries.map((e) => e.country))).sort()];

  const filtered = entries.filter((e) => {
    if (categoryFilter !== ALL && e.category !== categoryFilter) return false;
    if (countryFilter !== ALL && e.country !== countryFilter) return false;
    return true;
  });

  const handleDeploy = async (entry: CatalogEntry) => {
    if (!user?.tenant_id) {
      toast.error('No tenant', 'A tenant is required to deploy an API');
      return;
    }
    setDeploying(true);
    try {
      await backendApisService.createBackendApi(user.tenant_id, {
        name: toSlug(entry.name),
        display_name: entry.display_name,
        description: entry.description,
        backend_url: entry.spec_url ?? entry.mcp_endpoint ?? '',
        openapi_spec_url: entry.protocol === 'openapi' ? entry.spec_url : undefined,
        auth_type: toBackendAuthType(entry.auth_type),
      });
      toast.success('API deployed', `${entry.display_name} added as draft backend API`);
      queryClient.invalidateQueries({ queryKey: ['backend-apis', user.tenant_id] });
      setDeployEntry(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Deploy failed';
      toast.error('Deploy failed', msg);
    } finally {
      setDeploying(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-72 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white flex items-center gap-2">
            <Globe className="h-6 w-6 text-primary-600" />
            EU Public API Catalog
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            {data?.total ?? 0} curated EU public APIs — deploy in one click
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
          Failed to load catalog. Check that the API is reachable.
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        {/* Category tabs */}
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setCategoryFilter(ALL)}
            className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
              categoryFilter === ALL
                ? 'bg-primary-600 text-white'
                : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700'
            }`}
          >
            All
          </button>
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setCategoryFilter(cat.id)}
              className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
                categoryFilter === cat.id
                  ? 'bg-primary-600 text-white'
                  : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700'
              }`}
            >
              {cat.name}
            </button>
          ))}
        </div>

        {/* Country select */}
        <select
          value={countryFilter}
          onChange={(e) => setCountryFilter(e.target.value)}
          className="px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
          aria-label="Filter by country"
        >
          <option value={ALL}>All countries</option>
          {countries
            .filter((c) => c !== ALL)
            .map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
        </select>
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="default"
            title="No APIs match your filters"
            description="Try selecting a different category or country."
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((entry) => (
            <CatalogCard key={entry.id} entry={entry} onDeploy={() => setDeployEntry(entry)} />
          ))}
        </div>
      )}

      {/* Deploy confirm dialog */}
      {deployEntry && (
        <DeployDialog
          entry={deployEntry}
          loading={deploying}
          onConfirm={() => handleDeploy(deployEntry)}
          onClose={() => setDeployEntry(null)}
        />
      )}
    </div>
  );
}

// ─── Catalog Card ─────────────────────────────────────────────────────────────

interface CatalogCardProps {
  entry: CatalogEntry;
  onDeploy: () => void;
}

function CatalogCard({ entry, onDeploy }: CatalogCardProps) {
  const status = statusConfig[entry.status] ?? statusConfig.community;
  const StatusIcon = status.icon;

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-5 hover:shadow-md transition-shadow flex flex-col">
      {/* Title row */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-base font-semibold text-neutral-900 dark:text-white leading-tight">
          {entry.display_name}
        </h3>
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${status.className}`}
        >
          <StatusIcon className="h-3 w-3" />
          {status.label}
        </span>
      </div>

      {/* Description */}
      <p className="text-sm text-neutral-500 dark:text-neutral-400 line-clamp-2 mb-3 flex-1">
        {entry.description}
      </p>

      {/* Tags */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        <span className="px-2 py-0.5 rounded text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
          {entry.country}
        </span>
        <span className="px-2 py-0.5 rounded text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 uppercase">
          {entry.protocol}
        </span>
        {entry.auth_type !== 'none' && (
          <span className="px-2 py-0.5 rounded text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
            {entry.auth_type}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2 pt-3 border-t dark:border-neutral-700">
        <button
          onClick={onDeploy}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Rocket className="h-4 w-4" />
          Deploy
        </button>
        {entry.documentation_url && (
          <a
            href={entry.documentation_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
            aria-label="View documentation"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
      </div>
    </div>
  );
}

// ─── Deploy Dialog ────────────────────────────────────────────────────────────

interface DeployDialogProps {
  entry: CatalogEntry;
  loading: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

function DeployDialog({ entry, loading, onConfirm, onClose }: DeployDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Deploy {entry.display_name}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-500"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            This will register{' '}
            <strong className="text-neutral-900 dark:text-white">{entry.display_name}</strong> as a
            draft backend API in your tenant.
          </p>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-neutral-500 dark:text-neutral-400">API name</dt>
            <dd className="text-neutral-900 dark:text-white font-mono text-xs">
              {toSlug(entry.name)}
            </dd>
            <dt className="text-neutral-500 dark:text-neutral-400">Protocol</dt>
            <dd className="text-neutral-900 dark:text-white uppercase">{entry.protocol}</dd>
            <dt className="text-neutral-500 dark:text-neutral-400">Auth</dt>
            <dd className="text-neutral-900 dark:text-white">{entry.auth_type}</dd>
            {entry.spec_url && (
              <>
                <dt className="text-neutral-500 dark:text-neutral-400">Spec URL</dt>
                <dd className="text-neutral-900 dark:text-white font-mono text-xs break-all">
                  {entry.spec_url}
                </dd>
              </>
            )}
          </dl>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Deploying...
              </>
            ) : (
              <>
                <Rocket className="h-4 w-4" />
                Confirm Deploy
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
