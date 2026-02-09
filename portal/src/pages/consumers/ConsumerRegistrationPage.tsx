/**
 * Consumer Registration Page
 *
 * Full-page form to register a new consumer with plan selection (CAB-1121).
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useCreateConsumer } from '../../hooks/useConsumers';
import { usePlans } from '../../hooks/usePlans';
import { PlanSelector } from '../../components/consumers/PlanSelector';
import type { ConsumerCreateRequest, Plan } from '../../types';

export function ConsumerRegistrationPage() {
  const { user } = useAuth();
  const tenantId = user?.tenant_id || '';

  const [name, setName] = useState('');
  const [externalId, setExternalId] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [description, setDescription] = useState('');
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const createMutation = useCreateConsumer(tenantId);
  const { data: plansData, isLoading: plansLoading } = usePlans(tenantId || undefined, {
    status: 'active',
  });

  const plans = plansData?.items || [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);

    const data: ConsumerCreateRequest = {
      name: name.trim(),
      external_id: externalId.trim(),
      email: email.trim(),
      company: company.trim() || undefined,
      description: description.trim() || undefined,
    };

    try {
      await createMutation.mutateAsync(data);
      setIsSuccess(true);
    } catch (err) {
      setCreateError((err as Error)?.message || 'Failed to register consumer');
    }
  };

  // Success state
  if (isSuccess) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-8 text-center">
          <div className="inline-flex p-4 bg-green-100 dark:bg-green-900/30 rounded-full mb-4">
            <CheckCircle className="h-8 w-8 text-green-500" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            Consumer Registered Successfully
          </h2>
          <p className="text-gray-500 dark:text-neutral-400 mb-6">
            The consumer &quot;{name}&quot; has been registered. You can now manage their API access
            from the consumers list.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link
              to="/workspace?tab=consumers"
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              View Consumers
            </Link>
            <button
              onClick={() => {
                setName('');
                setExternalId('');
                setEmail('');
                setCompany('');
                setDescription('');
                setSelectedPlan(null);
                setIsSuccess(false);
              }}
              className="px-4 py-2 border border-gray-300 dark:border-neutral-600 text-gray-700 dark:text-neutral-300 rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors"
            >
              Register Another
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Back link */}
      <Link
        to="/workspace?tab=consumers"
        className="inline-flex items-center text-sm text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-white"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Consumers
      </Link>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Register New Consumer</h1>
        <p className="text-gray-500 dark:text-neutral-400 mt-1">
          Register an external API consumer with OAuth credentials
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Error */}
        {createError && (
          <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{createError}</p>
          </div>
        )}

        {/* Consumer Details */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Consumer Details</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="reg-name"
                className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
              >
                Name <span className="text-red-500">*</span>
              </label>
              <input
                id="reg-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ACME Corp"
                required
                disabled={createMutation.isPending}
                className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
              />
            </div>

            <div>
              <label
                htmlFor="reg-external-id"
                className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
              >
                External ID <span className="text-red-500">*</span>
              </label>
              <input
                id="reg-external-id"
                type="text"
                value={externalId}
                onChange={(e) => setExternalId(e.target.value)}
                placeholder="partner-acme-001"
                required
                disabled={createMutation.isPending}
                className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
              />
            </div>

            <div>
              <label
                htmlFor="reg-email"
                className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
              >
                Contact Email <span className="text-red-500">*</span>
              </label>
              <input
                id="reg-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="api@acme.com"
                required
                disabled={createMutation.isPending}
                className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
              />
            </div>

            <div>
              <label
                htmlFor="reg-company"
                className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
              >
                Company
              </label>
              <input
                id="reg-company"
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="ACME Corporation"
                disabled={createMutation.isPending}
                className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="reg-description"
              className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
            >
              Description
            </label>
            <textarea
              id="reg-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this API consumer..."
              rows={3}
              disabled={createMutation.isPending}
              className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50 resize-none"
            />
          </div>
        </div>

        {/* Plan Selection */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
            Select a Plan
          </h3>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mb-4">
            Choose a subscription plan for this consumer (optional)
          </p>
          <PlanSelector
            plans={plans}
            selectedPlanId={selectedPlan?.id}
            onSelect={setSelectedPlan}
            isLoading={plansLoading}
          />
        </div>

        {/* Submit */}
        <div className="flex items-center justify-end gap-3">
          <Link
            to="/workspace?tab=consumers"
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
          >
            Cancel
          </Link>
          <button
            type="submit"
            disabled={
              createMutation.isPending || !name.trim() || !externalId.trim() || !email.trim()
            }
            className="inline-flex items-center gap-2 px-6 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {createMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Registering...
              </>
            ) : (
              'Register Consumer'
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

export default ConsumerRegistrationPage;
