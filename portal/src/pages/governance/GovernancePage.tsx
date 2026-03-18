/**
 * Governance Page (CAB-1525)
 *
 * Centralized governance view for tenant-admins and cpi-admins:
 * - Approval queue for pending subscription requests
 * - API lifecycle overview (draft/published/deprecated)
 * - Governance statistics dashboard
 */

import { useState } from 'react';
import { CheckCircle, XCircle, Clock, ShieldCheck, FileText, BarChart3 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { PermissionGate } from '../../components/common';
import {
  useGovernanceStats,
  usePendingApprovals,
  useApproveRequest,
  useRejectRequest,
} from '../../hooks/useGovernance';
import type { GovernanceApproval } from '../../types';

type GovernanceTab = 'approvals' | 'lifecycle' | 'overview';

function StatCard({
  label,
  value,
  icon: Icon,
  variant = 'default',
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  variant?: 'default' | 'warning' | 'success';
}) {
  const colors = {
    default: 'bg-neutral-50 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300',
    warning: 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400',
    success: 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400',
  };

  return (
    <div className={`rounded-lg p-4 ${colors[variant]}`}>
      <div className="flex items-center gap-3">
        <Icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
        <div>
          <p className="text-2xl font-semibold">{value}</p>
          <p className="text-sm opacity-75">{label}</p>
        </div>
      </div>
    </div>
  );
}

function ApprovalRow({
  approval,
  onApprove,
  onReject,
  isProcessing,
}: {
  approval: GovernanceApproval;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  isProcessing: boolean;
}) {
  return (
    <div className="flex items-center justify-between p-4 border-b border-neutral-100 dark:border-neutral-800 last:border-b-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
          {approval.details}
        </p>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
          Requested by {approval.requester_name} ({approval.requester_email})
        </p>
        <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">
          {new Date(approval.created_at).toLocaleDateString()}
        </p>
      </div>
      <div className="flex items-center gap-2 ml-4">
        <button
          onClick={() => onApprove(approval.id)}
          disabled={isProcessing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 rounded-md hover:bg-green-100 dark:hover:bg-green-900/40 disabled:opacity-50 transition-colors"
          aria-label={`Approve ${approval.resource_name}`}
        >
          <CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />
          Approve
        </button>
        <button
          onClick={() => onReject(approval.id)}
          disabled={isProcessing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-50 transition-colors"
          aria-label={`Reject ${approval.resource_name}`}
        >
          <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
          Reject
        </button>
      </div>
    </div>
  );
}

function ApprovalQueue() {
  const { data, isLoading, error } = usePendingApprovals();
  const approveMutation = useApproveRequest();
  const rejectMutation = useRejectRequest();

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-neutral-100 dark:bg-neutral-800 rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-8 text-red-600 dark:text-red-400">
        <p>Failed to load approvals. Please try again.</p>
      </div>
    );
  }

  const approvals = data?.items || [];

  if (approvals.length === 0) {
    return (
      <div className="text-center py-12">
        <CheckCircle className="h-12 w-12 text-green-400 mx-auto mb-3" aria-hidden="true" />
        <p className="text-neutral-600 dark:text-neutral-400 font-medium">All caught up!</p>
        <p className="text-sm text-neutral-500 dark:text-neutral-500 mt-1">
          No pending approvals at this time.
        </p>
      </div>
    );
  }

  const isProcessing = approveMutation.isPending || rejectMutation.isPending;

  return (
    <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-800">
      <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
        <h3 className="text-sm font-medium text-neutral-900 dark:text-white">
          Pending Approvals ({data?.total || 0})
        </h3>
      </div>
      {approvals.map((approval) => (
        <ApprovalRow
          key={approval.id}
          approval={approval}
          onApprove={(id) => approveMutation.mutate({ id })}
          onReject={(id) => rejectMutation.mutate({ id })}
          isProcessing={isProcessing}
        />
      ))}
    </div>
  );
}

function LifecycleOverview() {
  const { data: stats, isLoading } = useGovernanceStats();

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 bg-neutral-100 dark:bg-neutral-800 rounded-lg" />
        ))}
      </div>
    );
  }

  const apisByStatus = stats?.apis_by_status || {};
  const statuses = [
    { key: 'draft', label: 'Draft', color: 'bg-neutral-200 dark:bg-neutral-700' },
    { key: 'published', label: 'Published', color: 'bg-green-200 dark:bg-green-900/40' },
    { key: 'deprecated', label: 'Deprecated', color: 'bg-amber-200 dark:bg-amber-900/40' },
  ];
  const total = Object.values(apisByStatus).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      {/* Status distribution */}
      <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
        <h3 className="text-sm font-medium text-neutral-900 dark:text-white mb-4">
          API Lifecycle Distribution
        </h3>
        {total > 0 ? (
          <>
            <div className="flex rounded-full overflow-hidden h-3 mb-4">
              {statuses.map(({ key, color }) => {
                const count = apisByStatus[key] || 0;
                const pct = total > 0 ? (count / total) * 100 : 0;
                return pct > 0 ? (
                  <div
                    key={key}
                    className={color}
                    style={{ width: `${pct}%` }}
                    title={`${key}: ${count}`}
                  />
                ) : null;
              })}
            </div>
            <div className="grid grid-cols-3 gap-4">
              {statuses.map(({ key, label, color }) => (
                <div key={key} className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${color}`} />
                  <span className="text-sm text-neutral-600 dark:text-neutral-400">
                    {label}: {apisByStatus[key] || 0}
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No APIs registered yet.</p>
        )}
      </div>

      {/* Lifecycle transition rules */}
      <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
        <h3 className="text-sm font-medium text-neutral-900 dark:text-white mb-3">
          Lifecycle Rules
        </h3>
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
            <span className="px-2 py-0.5 bg-neutral-100 dark:bg-neutral-800 rounded text-xs">
              Draft
            </span>
            <span>&rarr;</span>
            <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 rounded text-xs">
              Published
            </span>
            <span className="text-xs text-amber-600 dark:text-amber-400 ml-2">
              Requires approval
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
            <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 rounded text-xs">
              Published
            </span>
            <span>&rarr;</span>
            <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-xs">
              Deprecated
            </span>
            <span className="text-xs text-neutral-500 dark:text-neutral-500 ml-2">
              Auto-approved
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
            <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-xs">
              Deprecated
            </span>
            <span>&rarr;</span>
            <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 rounded text-xs">
              Published
            </span>
            <span className="text-xs text-amber-600 dark:text-amber-400 ml-2">
              Requires approval
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function GovernancePage() {
  const [activeTab, setActiveTab] = useState<GovernanceTab>('approvals');
  const { data: stats } = useGovernanceStats();
  const { hasRole } = useAuth();

  const tabs: { id: GovernanceTab; label: string; icon: React.ElementType }[] = [
    { id: 'approvals', label: 'Approvals', icon: Clock },
    { id: 'lifecycle', label: 'API Lifecycle', icon: FileText },
    { id: 'overview', label: 'Overview', icon: BarChart3 },
  ];

  return (
    <PermissionGate
      permissions={['apis:update', 'users:manage']}
      fallback={
        <div className="text-center py-12">
          <ShieldCheck className="h-12 w-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
          <p className="text-neutral-600 dark:text-neutral-400">
            You don&apos;t have permission to access governance features.
          </p>
        </div>
      }
    >
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Governance</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Manage API approvals, lifecycle policies, and access control.
          </p>
        </div>

        {/* Stats row */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard
              label="Pending Approvals"
              value={stats.pending_approvals}
              icon={Clock}
              variant={stats.pending_approvals > 0 ? 'warning' : 'default'}
            />
            <StatCard
              label="Published APIs"
              value={stats.apis_by_status['published'] || 0}
              icon={CheckCircle}
              variant="success"
            />
            <StatCard
              label="Draft APIs"
              value={stats.apis_by_status['draft'] || 0}
              icon={FileText}
            />
            <StatCard
              label="Deprecated"
              value={stats.apis_by_status['deprecated'] || 0}
              icon={XCircle}
            />
          </div>
        )}

        {/* Tabs */}
        <div className="border-b border-neutral-200 dark:border-neutral-800 mb-6">
          <nav className="flex gap-6" aria-label="Governance tabs">
            {tabs.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === id
                    ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                    : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {label}
                {id === 'approvals' && stats && stats.pending_approvals > 0 && (
                  <span className="ml-1 px-1.5 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded-full">
                    {stats.pending_approvals}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab content */}
        {activeTab === 'approvals' && <ApprovalQueue />}
        {activeTab === 'lifecycle' && <LifecycleOverview />}
        {activeTab === 'overview' && (
          <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-800 p-6">
            <h3 className="text-sm font-medium text-neutral-900 dark:text-white mb-3">
              Governance Overview
            </h3>
            <div className="space-y-3 text-sm text-neutral-600 dark:text-neutral-400">
              <p>
                <strong>Role:</strong>{' '}
                {hasRole('cpi-admin') ? 'Platform Administrator' : 'Tenant Administrator'}
              </p>
              <p>
                Governance controls ensure APIs follow your organization&apos;s approval workflows
                and lifecycle policies before being published to consumers.
              </p>
              <ul className="list-disc list-inside space-y-1 mt-2">
                <li>Subscription requests require admin approval when plans are configured</li>
                <li>API publication follows draft &rarr; published &rarr; deprecated lifecycle</li>
                <li>Deprecated APIs can be restored with admin approval</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </PermissionGate>
  );
}
