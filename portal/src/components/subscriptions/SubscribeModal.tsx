// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Subscribe Modal Component
 *
 * Modal form for subscribing an application to an API.
 */

import { useState, useEffect } from 'react';
import { X, Loader2, AlertCircle, Check, Zap, Crown, Building2 } from 'lucide-react';
import { useApplications } from '../../hooks/useApplications';
import type { API, Application } from '../../types';

type SubscriptionPlan = 'free' | 'basic' | 'premium' | 'enterprise';

export interface SubscribeFormData {
  applicationId: string;
  applicationName: string;
  apiId: string;
  plan: SubscriptionPlan;
}

interface SubscribeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: SubscribeFormData) => Promise<void>;
  api: API;
  isLoading?: boolean;
  error?: string | null;
}

interface PlanInfo {
  name: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  features: string[];
  color: string;
  bgColor: string;
  borderColor: string;
}

const plans: Record<SubscriptionPlan, PlanInfo> = {
  free: {
    name: 'Free',
    description: 'For testing and development',
    icon: Check,
    features: ['100 requests/day', 'Basic support', 'Community access'],
    color: 'text-gray-700',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
  },
  basic: {
    name: 'Basic',
    description: 'For small projects',
    icon: Zap,
    features: ['10,000 requests/day', 'Email support', 'Standard SLA'],
    color: 'text-blue-700',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  premium: {
    name: 'Premium',
    description: 'For production workloads',
    icon: Crown,
    features: ['100,000 requests/day', 'Priority support', '99.9% SLA'],
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  enterprise: {
    name: 'Enterprise',
    description: 'For large-scale deployments',
    icon: Building2,
    features: ['Unlimited requests', 'Dedicated support', 'Custom SLA'],
    color: 'text-amber-700',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
  },
};

export function SubscribeModal({
  isOpen,
  onClose,
  onSubmit,
  api,
  isLoading = false,
  error = null,
}: SubscribeModalProps) {
  const [selectedAppId, setSelectedAppId] = useState<string>('');
  const [selectedPlan, setSelectedPlan] = useState<SubscriptionPlan>('free');

  const { data: applications, isLoading: appsLoading } = useApplications();

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedAppId('');
      setSelectedPlan('free');
    }
  }, [isOpen]);

  // Auto-select first app if only one exists
  useEffect(() => {
    if (applications?.items.length === 1 && !selectedAppId) {
      setSelectedAppId(applications.items[0].id);
    }
  }, [applications, selectedAppId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAppId) return;

    // Find selected application to get its name
    const selectedApp = activeApps.find((app: Application) => app.id === selectedAppId);
    if (!selectedApp) return;

    await onSubmit({
      applicationId: selectedAppId,
      applicationName: selectedApp.name,
      apiId: api.id,
      plan: selectedPlan,
    });
  };

  const handleClose = () => {
    if (!isLoading) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const activeApps = applications?.items.filter((app: Application) => app.status === 'active') || [];

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={handleClose}
        onKeyDown={(e) => e.key === 'Escape' && handleClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">
                Subscribe to API
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                {api.name} v{api.version}
              </p>
            </div>
            <button
              onClick={handleClose}
              disabled={isLoading}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="p-6 space-y-6">
              {/* Error message */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}

              {/* Select Application */}
              <div>
                <label htmlFor="application" className="block text-sm font-medium text-gray-700 mb-2">
                  Select Application <span className="text-red-500">*</span>
                </label>
                {appsLoading ? (
                  <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
                    <Loader2 className="h-4 w-4 animate-spin text-gray-500" />
                    <span className="text-sm text-gray-500">Loading applications...</span>
                  </div>
                ) : activeApps.length === 0 ? (
                  <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                    <p className="text-sm text-amber-700">
                      You don't have any active applications. Please create an application first
                      before subscribing to APIs.
                    </p>
                    <a
                      href="/apps"
                      className="mt-2 inline-block text-sm font-medium text-amber-800 hover:text-amber-900"
                    >
                      Go to My Applications →
                    </a>
                  </div>
                ) : (
                  <select
                    id="application"
                    value={selectedAppId}
                    onChange={(e) => setSelectedAppId(e.target.value)}
                    disabled={isLoading}
                    required
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
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
              <div role="radiogroup" aria-labelledby="plan-label">
                <span id="plan-label" className="block text-sm font-medium text-gray-700 mb-3">
                  Select Plan <span className="text-red-500" aria-hidden="true">*</span>
                  <span className="sr-only">(required)</span>
                </span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {(Object.keys(plans) as SubscriptionPlan[]).map((planKey) => {
                    const plan = plans[planKey];
                    const Icon = plan.icon;
                    const isSelected = selectedPlan === planKey;

                    return (
                      <button
                        key={planKey}
                        type="button"
                        onClick={() => setSelectedPlan(planKey)}
                        disabled={isLoading}
                        className={`relative p-4 rounded-lg border-2 text-left transition-all ${
                          isSelected
                            ? `${plan.borderColor} ${plan.bgColor} ring-2 ring-offset-1 ring-primary-500`
                            : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`p-2 rounded-lg ${plan.bgColor}`}>
                            <Icon className={`h-5 w-5 ${plan.color}`} />
                          </div>
                          <div className="flex-1">
                            <h4 className={`font-semibold ${isSelected ? plan.color : 'text-gray-900'}`}>
                              {plan.name}
                            </h4>
                            <p className="text-xs text-gray-500 mt-0.5">
                              {plan.description}
                            </p>
                            <ul className="mt-2 space-y-1">
                              {plan.features.map((feature, idx) => (
                                <li key={idx} className="flex items-center gap-1.5 text-xs text-gray-600">
                                  <Check className="h-3 w-3 text-green-500" />
                                  {feature}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                        {isSelected && (
                          <div className="absolute top-2 right-2">
                            <div className="p-1 bg-primary-600 rounded-full">
                              <Check className="h-3 w-3 text-white" />
                            </div>
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Info box */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <p className="text-sm text-blue-700">
                  After subscribing, you can use your application's credentials to access this API.
                  You can change your plan or cancel the subscription at any time.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !selectedAppId || activeApps.length === 0}
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

export default SubscribeModal;
