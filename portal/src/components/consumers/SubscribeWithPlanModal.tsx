/**
 * Subscribe With Plan Modal
 *
 * Subscription modal that uses real plans from the API instead of hardcoded tiers.
 *
 * Reference: CAB-1121 Phase 5
 */

import { useState, useEffect, useMemo } from 'react';
import { X, Loader2, AlertCircle, ShieldCheck } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useApplications } from '../../hooks/useApplications';
import { usePlans } from '../../hooks/usePlans';
import { PlanSelector } from './PlanSelector';
import type { API, Application } from '../../types';

export interface SubscribeWithPlanFormData {
  applicationId: string;
  applicationName: string;
  apiId: string;
  planId: string;
  planName: string;
}

interface SubscribeWithPlanModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: SubscribeWithPlanFormData) => Promise<void>;
  api: API;
  isLoading?: boolean;
  error?: string | null;
}

export function SubscribeWithPlanModal({
  isOpen,
  onClose,
  onSubmit,
  api,
  isLoading = false,
  error = null,
}: SubscribeWithPlanModalProps) {
  const { user } = useAuth();
  const [selectedAppId, setSelectedAppId] = useState<string>('');
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);

  const { data: applications, isLoading: appsLoading } = useApplications();
  const { data: plansData, isLoading: plansLoading } = usePlans(user?.tenant_id);

  const activePlans = useMemo(
    () => plansData?.items.filter((p) => p.status === 'active') || [],
    [plansData]
  );

  useEffect(() => {
    if (isOpen) {
      setSelectedAppId('');
      setSelectedPlanId(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (applications?.items.length === 1 && !selectedAppId) {
      setSelectedAppId(applications.items[0].id);
    }
  }, [applications, selectedAppId]);

  // Auto-select first plan if only one
  useEffect(() => {
    if (activePlans.length === 1 && !selectedPlanId) {
      setSelectedPlanId(activePlans[0].id);
    }
  }, [activePlans, selectedPlanId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAppId || !selectedPlanId) return;

    const selectedApp = activeApps.find((app: Application) => app.id === selectedAppId);
    const selectedPlan = activePlans.find((p) => p.id === selectedPlanId);
    if (!selectedApp || !selectedPlan) return;

    await onSubmit({
      applicationId: selectedAppId,
      applicationName: selectedApp.name,
      apiId: api.id,
      planId: selectedPlan.id,
      planName: selectedPlan.name,
    });
  };

  const handleClose = () => {
    if (!isLoading) onClose();
  };

  if (!isOpen) return null;

  const activeApps =
    applications?.items.filter((app: Application) => app.status === 'active') || [];
  const selectedPlan = activePlans.find((p) => p.id === selectedPlanId);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={handleClose}
        onKeyDown={(e) => e.key === 'Escape' && handleClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />

      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-neutral-700">
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Subscribe to API
              </h2>
              <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
                {api.name} v{api.version}
              </p>
            </div>
            <button
              onClick={handleClose}
              disabled={isLoading}
              className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="p-6 space-y-6">
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                  <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                </div>
              )}

              {/* Select Application */}
              <div>
                <label
                  htmlFor="application"
                  className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2"
                >
                  Application <span className="text-red-500">*</span>
                </label>
                {appsLoading ? (
                  <div className="flex items-center gap-2 p-3 bg-gray-50 dark:bg-neutral-900 rounded-lg">
                    <Loader2 className="h-4 w-4 animate-spin text-gray-500" />
                    <span className="text-sm text-gray-500 dark:text-neutral-400">
                      Loading applications...
                    </span>
                  </div>
                ) : activeApps.length === 0 ? (
                  <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                    <p className="text-sm text-amber-700 dark:text-amber-300">
                      No active applications. Create an application first.
                    </p>
                    <a
                      href="/workspace?tab=apps"
                      className="mt-2 inline-block text-sm font-medium text-amber-800 dark:text-amber-200 hover:underline"
                    >
                      Go to My Apps
                    </a>
                  </div>
                ) : (
                  <select
                    id="application"
                    value={selectedAppId}
                    onChange={(e) => setSelectedAppId(e.target.value)}
                    disabled={isLoading}
                    required
                    className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
                  >
                    <option value="">Select an application...</option>
                    {activeApps.map((app: Application) => (
                      <option key={app.id} value={app.id}>
                        {app.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Select Plan */}
              <div>
                <span
                  id="plan-label"
                  className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-3"
                >
                  Plan <span className="text-red-500">*</span>
                </span>
                <PlanSelector
                  plans={activePlans}
                  selectedPlanId={selectedPlanId}
                  onSelect={setSelectedPlanId}
                  isLoading={plansLoading}
                  disabled={isLoading}
                />
              </div>

              {/* Approval notice */}
              {selectedPlan?.requires_approval && (
                <div className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                  <ShieldCheck className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-blue-700 dark:text-blue-300">
                    This plan requires admin approval. Your subscription will be pending until
                    approved.
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-neutral-700">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !selectedAppId || !selectedPlanId || activeApps.length === 0}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Subscribing...
                  </>
                ) : (
                  'Subscribe'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default SubscribeWithPlanModal;
