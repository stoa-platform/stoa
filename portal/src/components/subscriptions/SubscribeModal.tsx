/**
 * Subscribe Modal Component
 *
 * Modal form for subscribing an application to an API.
 */

import { useState, useEffect } from 'react';
import { X, Loader2, AlertCircle, Check, Zap, Crown, Building2, Shield } from 'lucide-react';
import { Button } from '@stoa/shared/components/Button';
import { useApplications } from '../../hooks/useApplications';
import { CertificateUploader } from './CertificateUploader';
import type { CertificateValidationResult } from '../../services/certificateValidator';
import type { API, Application } from '../../types';

type SubscriptionPlan = 'free' | 'basic' | 'premium' | 'enterprise';

export interface CustomPlan {
  slug: string;
  name: string;
  description: string;
  features: string[];
}

export interface SubscribeFormData {
  applicationId: string;
  applicationName: string;
  apiId: string;
  plan: string;
  certificateFingerprint?: string;
}

interface SubscribeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: SubscribeFormData) => Promise<void>;
  api: API;
  isLoading?: boolean;
  error?: string | null;
  /** Override default plans with API-specific plans (e.g. Chat Completions). */
  customPlans?: CustomPlan[];
  /** Pre-select a plan slug when opening the modal. */
  defaultPlan?: string;
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
    color: 'text-neutral-700',
    bgColor: 'bg-neutral-50',
    borderColor: 'border-neutral-200',
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
  customPlans,
  defaultPlan,
}: SubscribeModalProps) {
  const [selectedAppId, setSelectedAppId] = useState<string>('');
  const [selectedPlan, setSelectedPlan] = useState<string>('free');
  const [certResult, setCertResult] = useState<CertificateValidationResult | null>(null);

  const requiresMtls = api.tags?.includes('mtls') ?? false;
  const hasCustomPlans = customPlans && customPlans.length > 0;

  const { data: applications, isLoading: appsLoading } = useApplications();

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedAppId('');
      setSelectedPlan(defaultPlan ?? (hasCustomPlans ? customPlans[0].slug : 'free'));
      setCertResult(null);
    }
  }, [isOpen, defaultPlan, hasCustomPlans, customPlans]);

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
      certificateFingerprint: certResult?.certificate?.fingerprint_sha256,
    });
  };

  const handleClose = () => {
    if (!isLoading) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const activeApps =
    applications?.items.filter((app: Application) => app.status === 'active') || [];

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
        <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-neutral-200 dark:border-neutral-700">
            <div>
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">
                Subscribe to API
              </h2>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
                {api.name} v{api.version}
              </p>
            </div>
            <button
              onClick={handleClose}
              disabled={isLoading}
              className="p-2 text-neutral-400 dark:text-neutral-500 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="p-6 space-y-6">
              {/* Error message */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                  <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
                </div>
              )}

              {/* Select Application */}
              <div>
                <label
                  htmlFor="application"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2"
                >
                  Select Application <span className="text-red-500">*</span>
                </label>
                {appsLoading ? (
                  <div className="flex items-center gap-2 p-3 bg-neutral-50 dark:bg-neutral-900 rounded-lg">
                    <Loader2 className="h-4 w-4 animate-spin text-neutral-500 dark:text-neutral-400" />
                    <span className="text-sm text-neutral-500 dark:text-neutral-400">
                      Loading applications...
                    </span>
                  </div>
                ) : activeApps.length === 0 ? (
                  <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                    <p className="text-sm text-amber-700 dark:text-amber-400">
                      You don't have any active applications. Please create an application first
                      before subscribing to APIs.
                    </p>
                    <a
                      href="/apps"
                      className="mt-2 inline-block text-sm font-medium text-amber-800 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-200"
                    >
                      Go to My Applications &rarr;
                    </a>
                  </div>
                ) : (
                  <select
                    id="application"
                    value={selectedAppId}
                    onChange={(e) => setSelectedAppId(e.target.value)}
                    disabled={isLoading}
                    required
                    className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-neutral-100 dark:disabled:bg-neutral-700 disabled:cursor-not-allowed dark:bg-neutral-800 dark:text-white"
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
                <span
                  id="plan-label"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3"
                >
                  Select Plan{' '}
                  <span className="text-red-500" aria-hidden="true">
                    *
                  </span>
                  <span className="sr-only">(required)</span>
                </span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {hasCustomPlans
                    ? customPlans.map((cp) => {
                        const isSelected = selectedPlan === cp.slug;
                        return (
                          <button
                            key={cp.slug}
                            type="button"
                            onClick={() => setSelectedPlan(cp.slug)}
                            disabled={isLoading}
                            className={`relative p-4 rounded-lg border-2 text-left transition-all ${
                              isSelected
                                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 ring-2 ring-offset-1 ring-primary-500 dark:ring-offset-neutral-800'
                                : 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-800'
                            } disabled:opacity-50 disabled:cursor-not-allowed`}
                          >
                            <div className="flex-1">
                              <h4
                                className={`font-semibold ${isSelected ? 'text-primary-700 dark:text-primary-400' : 'text-neutral-900 dark:text-white'}`}
                              >
                                {cp.name}
                              </h4>
                              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                                {cp.description}
                              </p>
                              <ul className="mt-2 space-y-1">
                                {cp.features.map((feature, idx) => (
                                  <li
                                    key={idx}
                                    className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-400"
                                  >
                                    <Check className="h-3 w-3 text-green-500" />
                                    {feature}
                                  </li>
                                ))}
                              </ul>
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
                      })
                    : (Object.keys(plans) as SubscriptionPlan[]).map((planKey) => {
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
                                ? `${plan.borderColor} ${plan.bgColor} ring-2 ring-offset-1 ring-primary-500 dark:ring-offset-neutral-800`
                                : 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-800'
                            } disabled:opacity-50 disabled:cursor-not-allowed`}
                          >
                            <div className="flex items-start gap-3">
                              <div className={`p-2 rounded-lg ${plan.bgColor}`}>
                                <Icon className={`h-5 w-5 ${plan.color}`} />
                              </div>
                              <div className="flex-1">
                                <h4
                                  className={`font-semibold ${isSelected ? plan.color : 'text-neutral-900 dark:text-white'}`}
                                >
                                  {plan.name}
                                </h4>
                                <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                                  {plan.description}
                                </p>
                                <ul className="mt-2 space-y-1">
                                  {plan.features.map((feature, idx) => (
                                    <li
                                      key={idx}
                                      className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-400"
                                    >
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

              {/* mTLS Certificate Upload (conditional) */}
              {requiresMtls && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Shield className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                      Client Certificate{' '}
                      <span className="text-red-500" aria-hidden="true">
                        *
                      </span>
                    </span>
                  </div>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
                    This API requires mTLS. Upload your X.509 client certificate for
                    certificate-bound access tokens (RFC 8705).
                  </p>
                  <CertificateUploader
                    required
                    onCertificateValidated={setCertResult}
                    onCertificateCleared={() => setCertResult(null)}
                  />
                  {certResult?.certificate && (
                    <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                      Fingerprint: {certResult.certificate.fingerprint_sha256.substring(0, 24)}...
                    </p>
                  )}
                </div>
              )}

              {/* Info box */}
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <p className="text-sm text-blue-700 dark:text-blue-400">
                  After subscribing, you can use your application's credentials to access this API.
                  You can change your plan or cancel the subscription at any time.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-neutral-200 dark:border-neutral-700">
              <Button variant="secondary" onClick={handleClose} disabled={isLoading}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  !selectedAppId || activeApps.length === 0 || (requiresMtls && !certResult?.valid)
                }
                loading={isLoading}
              >
                {isLoading ? 'Subscribing...' : 'Subscribe'}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default SubscribeModal;
