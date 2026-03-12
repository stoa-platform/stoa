import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  FileText,
  Trash2,
  Edit2,
  Eye,
  ArrowLeft,
  Globe,
  Cpu,
  Hexagon,
  Server,
  Radio,
  ToggleLeft,
  ToggleRight,
  Send,
} from 'lucide-react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { ConfirmDialog } from '@stoa/shared/components/ConfirmDialog';
import { useToastActions } from '@stoa/shared/components/Toast';
import type {
  Contract,
  ContractCreate,
  ProtocolType,
  ContractStatus,
  GeneratedBinding,
} from '../types';
import { SubNav } from '../components/SubNav';
import { apiCatalogTabs } from '../components/subNavGroups';

const PROTOCOL_ORDER: ProtocolType[] = ['rest', 'mcp', 'graphql', 'grpc', 'kafka'];

const PROTOCOL_CONFIG: Record<
  ProtocolType,
  { label: string; color: string; bg: string; icon: typeof Globe }
> = {
  rest: { label: 'REST', color: 'text-green-700', bg: 'bg-green-100', icon: Globe },
  mcp: { label: 'MCP', color: 'text-purple-700', bg: 'bg-purple-100', icon: Cpu },
  graphql: { label: 'GraphQL', color: 'text-pink-700', bg: 'bg-pink-100', icon: Hexagon },
  grpc: { label: 'gRPC', color: 'text-blue-700', bg: 'bg-blue-100', icon: Server },
  kafka: { label: 'Kafka', color: 'text-orange-700', bg: 'bg-orange-100', icon: Radio },
};

const STATUS_STYLES: Record<ContractStatus, string> = {
  draft: 'bg-gray-100 text-gray-700',
  published: 'bg-green-100 text-green-700',
  deprecated: 'bg-yellow-100 text-yellow-700',
};

type View = 'list' | 'create' | 'detail';

export function Contracts() {
  const { t } = useTranslation();
  const { user, hasPermission, hasRole } = useAuth();
  const toast = useToastActions();

  const [contracts, setContracts] = useState<Contract[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>('list');
  const [selectedContract, setSelectedContract] = useState<Contract | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Contract | null>(null);
  const [tenants, setTenants] = useState<{ id: string; display_name: string }[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState('');

  const canWrite = hasPermission('apis:update');
  const isAdmin = hasRole('cpi-admin');
  const tenantId = user?.tenant_id || selectedTenantId;

  // Load tenants for admin
  useEffect(() => {
    if (isAdmin) {
      apiService.getTenants().then((list) => {
        setTenants(list);
        if (list.length > 0 && !selectedTenantId) {
          setSelectedTenantId(list[0].id);
        }
      });
    }
  }, [isAdmin, selectedTenantId]);

  const loadContracts = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const res = await apiService.getContracts(tenantId);
      setContracts(res.items);
    } catch {
      toast.error('Failed to load contracts');
    } finally {
      setLoading(false);
    }
  }, [tenantId, toast]);

  useEffect(() => {
    loadContracts();
  }, [loadContracts]);

  const handleDelete = async () => {
    if (!tenantId || !deleteTarget) return;
    try {
      await apiService.deleteContract(tenantId, deleteTarget.id);
      toast.success('Contract deleted');
      setDeleteTarget(null);
      loadContracts();
    } catch {
      toast.error('Failed to delete contract');
    }
  };

  const openDetail = (contract: Contract) => {
    setSelectedContract(contract);
    setView('detail');
  };

  if (view === 'create') {
    return (
      <CreateContractView
        tenantId={tenantId}
        onBack={() => setView('list')}
        onCreated={() => {
          setView('list');
          loadContracts();
        }}
      />
    );
  }

  if (view === 'detail' && selectedContract) {
    return (
      <ContractDetailView
        tenantId={tenantId}
        contract={selectedContract}
        canWrite={canWrite}
        onBack={() => {
          setView('list');
          loadContracts();
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            {t('contracts.title', 'Contracts')}
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {t('contracts.subtitle', 'Universal API Contracts — Define Once, Expose Everywhere')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isAdmin && tenants.length > 0 && (
            <select
              value={selectedTenantId}
              onChange={(e) => setSelectedTenantId(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.display_name}
                </option>
              ))}
            </select>
          )}
          {canWrite && tenantId && (
            <button
              onClick={() => setView('create')}
              className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Plus className="w-4 h-4" />
              {t('contracts.createContract', 'Create Contract')}
            </button>
          )}
        </div>
      </div>

      {/* Contextual sub-navigation (CAB-1785) */}
      <SubNav tabs={apiCatalogTabs} />

      {loading ? (
        <div className="text-center py-12 text-neutral-500">{t('common.loading')}</div>
      ) : contracts.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700">
          <FileText className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
          <p className="text-neutral-500 dark:text-neutral-400">
            {t('contracts.noContracts', 'No contracts configured')}
          </p>
          {canWrite && (
            <button
              onClick={() => setView('create')}
              className="mt-4 inline-flex items-center gap-2 text-blue-600 hover:text-blue-700"
            >
              <Plus className="w-4 h-4" />
              {t('contracts.createContract', 'Create Contract')}
            </button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {contracts.map((contract) => (
            <div
              key={contract.id}
              className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-blue-300 dark:hover:border-blue-600 transition-colors cursor-pointer"
              onClick={() => openDetail(contract)}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-neutral-900 dark:text-white truncate">
                    {contract.display_name}
                  </h3>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                    {contract.name}
                  </p>
                </div>
                <span
                  className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[contract.status]}`}
                >
                  {contract.status}
                </span>
              </div>

              {contract.description && (
                <p className="text-sm text-neutral-600 dark:text-neutral-300 mb-3 line-clamp-2">
                  {contract.description}
                </p>
              )}

              <div className="flex items-center gap-1.5 mb-3">
                {PROTOCOL_ORDER.map((proto) => {
                  const binding = contract.bindings.find((b) => b.protocol === proto);
                  const cfg = PROTOCOL_CONFIG[proto];
                  return (
                    <span
                      key={proto}
                      className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        binding?.enabled
                          ? `${cfg.bg} ${cfg.color}`
                          : 'bg-neutral-100 text-neutral-400 dark:bg-neutral-700 dark:text-neutral-500'
                      }`}
                    >
                      {cfg.label}
                    </span>
                  );
                })}
              </div>

              <div className="flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400">
                <span>v{contract.version}</span>
                <div className="flex gap-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      openDetail(contract);
                    }}
                    className="p-1 hover:text-blue-600"
                    title="View details"
                  >
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                  {canWrite && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget(contract);
                      }}
                      className="p-1 hover:text-red-600"
                      title="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('contracts.deleteContract', 'Delete Contract')}
        message={`Are you sure you want to delete "${deleteTarget?.display_name}"? This action cannot be undone.`}
        confirmLabel={t('common.delete')}
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

// ---- Create Contract View ----

function CreateContractView({
  tenantId,
  onBack,
  onCreated,
}: {
  tenantId: string | undefined;
  onBack: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToastActions();
  const [submitting, setSubmitting] = useState(false);
  const [publishResult, setPublishResult] = useState<GeneratedBinding[] | null>(null);

  const [form, setForm] = useState<ContractCreate>({
    name: '',
    display_name: '',
    description: '',
    version: '1.0.0',
    openapi_spec_url: '',
  });

  const handleSubmit = async (publish: boolean) => {
    if (!tenantId || !form.name || !form.display_name) return;
    setSubmitting(true);
    try {
      const payload: ContractCreate = {
        ...form,
        status: publish ? 'published' : 'draft',
      };
      const contract = await apiService.createContract(tenantId, payload);

      if (publish) {
        const res = await apiService.publishContract(tenantId, contract.id);
        setPublishResult(res.bindings_generated);
        toast.success('Contract published');
      } else {
        toast.success('Contract created as draft');
        onCreated();
      }
    } catch {
      toast.error('Failed to create contract');
    } finally {
      setSubmitting(false);
    }
  };

  if (publishResult) {
    return (
      <div className="space-y-6">
        <button onClick={onCreated} className="flex items-center gap-1 text-sm text-blue-600">
          <ArrowLeft className="w-4 h-4" /> Back to contracts
        </button>
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-green-200 dark:border-green-800 p-6">
          <h2 className="text-lg font-bold text-green-700 dark:text-green-400 mb-4">
            Contract Published Successfully
          </h2>
          <p className="text-sm text-neutral-600 dark:text-neutral-300 mb-4">
            The following protocol bindings were generated:
          </p>
          <div className="space-y-2">
            {publishResult.map((binding) => {
              const cfg = PROTOCOL_CONFIG[binding.protocol];
              return (
                <div
                  key={binding.protocol}
                  className="flex items-center gap-3 p-3 bg-neutral-50 dark:bg-neutral-700 rounded"
                >
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${cfg.bg} ${cfg.color}`}
                  >
                    {cfg.label}
                  </span>
                  <code className="text-sm text-neutral-600 dark:text-neutral-300 flex-1">
                    {binding.endpoint}
                  </code>
                  {binding.tool_name && (
                    <span className="text-xs text-neutral-500">tool: {binding.tool_name}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-blue-600">
        <ArrowLeft className="w-4 h-4" /> Back to contracts
      </button>

      <h2 className="text-xl font-bold text-neutral-900 dark:text-white">
        {t('contracts.createNewContract', 'Create New Contract')}
      </h2>

      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 space-y-4 max-w-2xl">
        <div>
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            Name (slug)
          </label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="my-api-contract"
            className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            Display Name
          </label>
          <input
            type="text"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            placeholder="My API Contract"
            className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            Description
          </label>
          <textarea
            value={form.description || ''}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
            className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Version
            </label>
            <input
              type="text"
              value={form.version}
              onChange={(e) => setForm({ ...form, version: e.target.value })}
              placeholder="1.0.0"
              className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              OpenAPI Spec URL
            </label>
            <input
              type="text"
              value={form.openapi_spec_url || ''}
              onChange={(e) => setForm({ ...form, openapi_spec_url: e.target.value })}
              placeholder="https://..."
              className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
            />
          </div>
        </div>

        <div className="flex gap-3 pt-4">
          <button
            onClick={() => handleSubmit(false)}
            disabled={submitting || !form.name || !form.display_name}
            className="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50 text-neutral-700 dark:text-neutral-300"
          >
            Save as Draft
          </button>
          <button
            onClick={() => handleSubmit(true)}
            disabled={submitting || !form.name || !form.display_name}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
            Create & Publish
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Contract Detail View ----

function ContractDetailView({
  tenantId,
  contract: initialContract,
  canWrite,
  onBack,
}: {
  tenantId: string | undefined;
  contract: Contract;
  canWrite: boolean;
  onBack: () => void;
}) {
  const toast = useToastActions();
  const [contract, setContract] = useState(initialContract);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    display_name: contract.display_name,
    description: contract.description || '',
    version: contract.version,
  });

  const refreshContract = useCallback(async () => {
    if (!tenantId) return;
    try {
      const updated = await apiService.getContract(tenantId, contract.id);
      setContract(updated);
    } catch {
      // keep stale data
    }
  }, [tenantId, contract.id]);

  const handleToggleBinding = async (protocol: ProtocolType, currentlyEnabled: boolean) => {
    if (!tenantId) return;
    try {
      if (currentlyEnabled) {
        await apiService.disableBinding(tenantId, contract.id, protocol);
        toast.success(`${PROTOCOL_CONFIG[protocol].label} binding disabled`);
      } else {
        await apiService.enableBinding(tenantId, contract.id, protocol);
        toast.success(`${PROTOCOL_CONFIG[protocol].label} binding enabled`);
      }
      refreshContract();
    } catch {
      toast.error('Failed to update binding');
    }
  };

  const handleSaveEdit = async () => {
    if (!tenantId) return;
    try {
      const updated = await apiService.updateContract(tenantId, contract.id, editForm);
      setContract(updated);
      setEditing(false);
      toast.success('Contract updated');
    } catch {
      toast.error('Failed to update contract');
    }
  };

  const handlePublish = async () => {
    if (!tenantId) return;
    try {
      const res = await apiService.publishContract(tenantId, contract.id);
      setContract(res.contract);
      toast.success('Contract published');
    } catch {
      toast.error('Failed to publish contract');
    }
  };

  return (
    <div className="space-y-6">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-blue-600">
        <ArrowLeft className="w-4 h-4" /> Back to contracts
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-neutral-900 dark:text-white">
            {contract.display_name}
          </h2>
          <p className="text-sm text-neutral-500 font-mono">{contract.name}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_STYLES[contract.status]}`}
          >
            {contract.status}
          </span>
          {canWrite && contract.status === 'draft' && (
            <button
              onClick={handlePublish}
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700"
            >
              <Send className="w-3.5 h-3.5" /> Publish
            </button>
          )}
          {canWrite && (
            <button
              onClick={() => setEditing(!editing)}
              className="p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded"
              title="Edit"
            >
              <Edit2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Edit form */}
      {editing && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-blue-200 dark:border-blue-800 p-4 space-y-3 max-w-2xl">
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Display Name
            </label>
            <input
              type="text"
              value={editForm.display_name}
              onChange={(e) => setEditForm({ ...editForm, display_name: e.target.value })}
              className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Description
            </label>
            <textarea
              value={editForm.description}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              rows={2}
              className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Version
            </label>
            <input
              type="text"
              value={editForm.version}
              onChange={(e) => setEditForm({ ...editForm, version: e.target.value })}
              className="w-full border rounded-lg px-3 py-2 dark:bg-neutral-700 dark:border-neutral-600 dark:text-white"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSaveEdit}
              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
            >
              Save
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-1.5 border border-neutral-300 dark:border-neutral-600 text-sm rounded-lg"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Contract info */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-neutral-500 dark:text-neutral-400">Version</dt>
            <dd className="font-medium text-neutral-900 dark:text-white">v{contract.version}</dd>
          </div>
          <div>
            <dt className="text-neutral-500 dark:text-neutral-400">Created</dt>
            <dd className="font-medium text-neutral-900 dark:text-white">
              {new Date(contract.created_at).toLocaleDateString()}
            </dd>
          </div>
          {contract.description && (
            <div className="col-span-2">
              <dt className="text-neutral-500 dark:text-neutral-400">Description</dt>
              <dd className="text-neutral-900 dark:text-white">{contract.description}</dd>
            </div>
          )}
          {contract.openapi_spec_url && (
            <div className="col-span-2">
              <dt className="text-neutral-500 dark:text-neutral-400">OpenAPI Spec</dt>
              <dd>
                <a
                  href={contract.openapi_spec_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline text-sm"
                >
                  {contract.openapi_spec_url}
                </a>
              </dd>
            </div>
          )}
        </dl>
      </div>

      {/* Protocol Bindings */}
      <div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-3">
          Protocol Bindings
        </h3>
        <div className="space-y-2">
          {PROTOCOL_ORDER.map((proto) => {
            const binding = contract.bindings.find((b) => b.protocol === proto);
            const cfg = PROTOCOL_CONFIG[proto];
            const Icon = cfg.icon;
            const enabled = binding?.enabled ?? false;

            return (
              <div
                key={proto}
                className="flex items-center justify-between p-3 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700"
              >
                <div className="flex items-center gap-3">
                  <div className={`p-1.5 rounded ${cfg.bg}`}>
                    <Icon className={`w-4 h-4 ${cfg.color}`} />
                  </div>
                  <div>
                    <span className="font-medium text-neutral-900 dark:text-white">
                      {cfg.label}
                    </span>
                    {binding?.endpoint && (
                      <p className="text-xs text-neutral-500 font-mono">{binding.endpoint}</p>
                    )}
                    {binding?.tool_name && (
                      <p className="text-xs text-neutral-400">tool: {binding.tool_name}</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {binding?.traffic_24h != null && (
                    <span className="text-xs text-neutral-400">
                      {binding.traffic_24h.toLocaleString()} req/24h
                    </span>
                  )}
                  {canWrite ? (
                    <button
                      onClick={() => handleToggleBinding(proto, enabled)}
                      className={`p-1 rounded transition-colors ${
                        enabled
                          ? 'text-green-600 hover:text-green-700'
                          : 'text-neutral-400 hover:text-neutral-500'
                      }`}
                      title={enabled ? 'Disable' : 'Enable'}
                    >
                      {enabled ? (
                        <ToggleRight className="w-6 h-6" />
                      ) : (
                        <ToggleLeft className="w-6 h-6" />
                      )}
                    </button>
                  ) : (
                    <span
                      className={`text-xs font-medium ${enabled ? 'text-green-600' : 'text-neutral-400'}`}
                    >
                      {enabled ? 'Active' : 'Inactive'}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
