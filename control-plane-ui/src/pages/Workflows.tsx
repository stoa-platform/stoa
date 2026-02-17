/**
 * Onboarding Workflows page (CAB-593)
 *
 * Two tabs: Templates (CRUD) + Instances (list, approve/reject).
 * RBAC: cpi-admin/tenant-admin = full access, devops/viewer = read-only.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle,
  FileText,
  Loader2,
  PlayCircle,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import type {
  WorkflowInstance,
  WorkflowMode,
  WorkflowStatus,
  WorkflowTemplate,
  WorkflowType,
} from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_STYLES: Record<string, { bg: string; text: string }> = {
  pending: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-800 dark:text-yellow-300',
  },
  in_progress: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-800 dark:text-blue-300' },
  approved: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300' },
  rejected: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-300' },
  provisioning: {
    bg: 'bg-purple-100 dark:bg-purple-900/30',
    text: 'text-purple-800 dark:text-purple-300',
  },
  completed: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-300',
  },
  failed: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-300' },
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style.bg} ${style.text}`}
    >
      {status.replace('_', ' ')}
    </span>
  );
}

function ModeBadge({ mode }: { mode: WorkflowMode }) {
  const labels: Record<WorkflowMode, string> = {
    auto: 'Auto',
    manual: 'Manual',
    approval_chain: 'Chain',
  };
  return (
    <span className="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-700 px-2.5 py-0.5 text-xs font-medium text-gray-700 dark:text-gray-300">
      {labels[mode]}
    </span>
  );
}

const TYPE_LABELS: Record<WorkflowType, string> = {
  user_registration: 'User Registration',
  consumer_registration: 'Consumer Registration',
  tenant_owner: 'Tenant Owner',
};

// ---------------------------------------------------------------------------
// Templates Tab
// ---------------------------------------------------------------------------

function TemplatesTab({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiService.listWorkflowTemplates(tenantId);
      setTemplates(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load templates');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleDelete = async (id: string) => {
    try {
      await apiService.deleteWorkflowTemplate(tenantId, id);
      await fetchTemplates();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-300">
        {error}
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">
          {templates.length} template{templates.length !== 1 ? 's' : ''}
        </h3>
        <div className="flex gap-2">
          <button
            onClick={fetchTemplates}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {templates.length === 0 ? (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <FileText className="mx-auto h-10 w-10 mb-3 opacity-50" />
          <p>No workflow templates yet.</p>
          {canManage && <p className="text-xs mt-1">Create a template to get started.</p>}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Mode
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Steps
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Sector
                </th>
                {canManage && (
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {templates.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">
                    {t.name}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                    {TYPE_LABELS[t.workflow_type] ?? t.workflow_type}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <ModeBadge mode={t.mode} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                    {t.approval_steps.length}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                    {t.sector ?? '—'}
                  </td>
                  {canManage && (
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDelete(t.id)}
                        className="text-red-500 hover:text-red-700 dark:hover:text-red-400"
                        title="Delete template"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Instances Tab
// ---------------------------------------------------------------------------

function InstancesTab({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [instances, setInstances] = useState<WorkflowInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const fetchInstances = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      const res = await apiService.listWorkflowInstances(tenantId, params);
      setInstances(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load instances');
    } finally {
      setLoading(false);
    }
  }, [tenantId, statusFilter]);

  useEffect(() => {
    fetchInstances();
  }, [fetchInstances]);

  const handleApprove = async (id: string) => {
    try {
      await apiService.approveWorkflowStep(tenantId, id);
      await fetchInstances();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Approve failed');
    }
  };

  const handleReject = async (id: string) => {
    try {
      await apiService.rejectWorkflowStep(tenantId, id);
      await fetchInstances();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Reject failed');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-300">
        {error}
      </div>
    );
  }

  const STATUSES: WorkflowStatus[] = [
    'pending',
    'in_progress',
    'approved',
    'rejected',
    'completed',
    'failed',
  ];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </select>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {instances.length} instance{instances.length !== 1 ? 's' : ''}
          </span>
        </div>
        <button
          onClick={fetchInstances}
          className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </button>
      </div>

      {instances.length === 0 ? (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <PlayCircle className="mx-auto h-10 w-10 mb-3 opacity-50" />
          <p>No workflow instances found.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Subject
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Step
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Created
                </th>
                {canManage && (
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {instances.map((inst) => (
                <tr key={inst.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-4 py-3 text-sm">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {inst.subject_email}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {inst.subject_id}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                    {TYPE_LABELS[inst.workflow_type] ?? inst.workflow_type}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <StatusBadge status={inst.status} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                    {inst.current_step_index}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                    {new Date(inst.created_at).toLocaleDateString()}
                  </td>
                  {canManage && (
                    <td className="px-4 py-3 text-right">
                      {(inst.status === 'pending' || inst.status === 'in_progress') && (
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => handleApprove(inst.id)}
                            className="text-green-600 hover:text-green-800 dark:hover:text-green-400"
                            title="Approve"
                          >
                            <CheckCircle className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleReject(inst.id)}
                            className="text-red-500 hover:text-red-700 dark:hover:text-red-400"
                            title="Reject"
                          >
                            <XCircle className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

type Tab = 'templates' | 'instances';

export function Workflows() {
  const { user, hasPermission } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>('templates');
  const tenantId = user?.tenant_id ?? '';
  const canManage = hasPermission('workflows:manage');

  const tabs: { id: Tab; label: string; icon: typeof FileText }[] = [
    { id: 'templates', label: 'Templates', icon: FileText },
    { id: 'instances', label: 'Instances', icon: PlayCircle },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Onboarding Workflows
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Manage approval workflows for user registration, consumer onboarding, and tenant setup.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex -mb-px space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 border-b-2 px-1 py-3 text-sm font-medium transition-colors ${
                  isActive
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'templates' && <TemplatesTab tenantId={tenantId} canManage={canManage} />}
      {activeTab === 'instances' && <InstancesTab tenantId={tenantId} canManage={canManage} />}
    </div>
  );
}
