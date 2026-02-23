/**
 * Consumer Registration Page
 *
 * Self-service registration form where developers register as API consumers.
 * After registration, OAuth2 credentials are displayed once.
 *
 * Reference: CAB-1121 Phase 5
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UserPlus, Loader2, AlertCircle, ArrowLeft } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useRegisterConsumer, useConsumerCredentials } from '../../hooks/useConsumers';
import { CredentialsModal } from '../../components/consumers/CredentialsModal';
import { useToastActions } from '@stoa/shared/components/Toast';
import type { ConsumerCredentials } from '../../types';

export function ConsumerRegistrationPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToastActions();
  const registerMutation = useRegisterConsumer();
  const credentialsMutation = useConsumerCredentials();

  const [form, setForm] = useState({
    external_id: '',
    name: '',
    email: user?.email || '',
    company: '',
    description: '',
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<ConsumerCredentials | null>(null);
  const [showCredentials, setShowCredentials] = useState(false);

  const tenantId = user?.tenant_id;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    setFormError(null);
  };

  // Auto-generate external_id from name
  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const name = e.target.value;
    setForm((prev) => ({
      ...prev,
      name,
      external_id:
        prev.external_id === '' || prev.external_id === slugify(prev.name)
          ? slugify(name)
          : prev.external_id,
    }));
    setFormError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tenantId) {
      setFormError('No tenant assigned. Contact your administrator.');
      return;
    }

    if (!form.external_id.match(/^[a-z0-9][a-z0-9-]*[a-z0-9]$/)) {
      setFormError('External ID must be lowercase alphanumeric with hyphens (e.g., "my-app-01")');
      return;
    }

    try {
      const consumer = await registerMutation.mutateAsync({
        tenantId,
        data: {
          external_id: form.external_id,
          name: form.name,
          email: form.email,
          company: form.company || undefined,
          description: form.description || undefined,
        },
      });

      // Fetch credentials for the new consumer
      const creds = await credentialsMutation.mutateAsync({
        tenantId,
        consumerId: consumer.id,
      });

      setCredentials(creds);
      setShowCredentials(true);
      toast.success('Consumer registered successfully');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Registration failed. Please try again.';
      if (message.includes('409') || message.includes('already exists')) {
        setFormError('A consumer with this external ID already exists in your tenant.');
      } else {
        setFormError(message);
      }
    }
  };

  const handleCredentialsClose = () => {
    setShowCredentials(false);
    navigate('/apis');
  };

  const isSubmitting = registerMutation.isPending || credentialsMutation.isPending;

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 mb-3 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary-50 dark:bg-primary-900/30 rounded-lg">
            <UserPlus className="h-6 w-6 text-primary-600 dark:text-primary-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
              Register as Consumer
            </h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
              Register to get OAuth2 credentials for API access
            </p>
          </div>
        </div>
      </div>

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="bg-white dark:bg-neutral-800 rounded-xl shadow-sm border border-neutral-200 dark:border-neutral-700"
      >
        <div className="p-6 space-y-5">
          {formError && (
            <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-700 dark:text-red-300">{formError}</p>
            </div>
          )}

          {/* Name */}
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Consumer Name <span className="text-red-500">*</span>
            </label>
            <input
              id="name"
              name="name"
              type="text"
              required
              value={form.name}
              onChange={handleNameChange}
              placeholder="My Application"
              disabled={isSubmitting}
              className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50 placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* External ID */}
          <div>
            <label
              htmlFor="external_id"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              External ID <span className="text-red-500">*</span>
            </label>
            <input
              id="external_id"
              name="external_id"
              type="text"
              required
              value={form.external_id}
              onChange={handleChange}
              placeholder="my-application"
              pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
              disabled={isSubmitting}
              className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white rounded-lg font-mono text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50 placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              Unique identifier. Lowercase, numbers, and hyphens only. Used in your client_id.
            </p>
          </div>

          {/* Email */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Email <span className="text-red-500">*</span>
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              value={form.email}
              onChange={handleChange}
              placeholder="dev@company.com"
              disabled={isSubmitting}
              className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50 placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Company */}
          <div>
            <label
              htmlFor="company"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Company
            </label>
            <input
              id="company"
              name="company"
              type="text"
              value={form.company}
              onChange={handleChange}
              placeholder="Acme Corp"
              disabled={isSubmitting}
              className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50 placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Description */}
          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Description
            </label>
            <textarea
              id="description"
              name="description"
              rows={3}
              value={form.description}
              onChange={handleChange}
              placeholder="Brief description of how you'll use the API..."
              disabled={isSubmitting}
              className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50 resize-none placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-neutral-200 dark:border-neutral-700">
          <button
            type="button"
            onClick={() => navigate(-1)}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting || !form.name || !form.external_id || !form.email}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Registering...
              </>
            ) : (
              <>
                <UserPlus className="h-4 w-4" />
                Register
              </>
            )}
          </button>
        </div>
      </form>

      {/* Credentials Modal */}
      {credentials && (
        <CredentialsModal
          isOpen={showCredentials}
          onClose={handleCredentialsClose}
          credentials={credentials}
          consumerName={form.name}
          tenantId={tenantId}
          consumerId={credentials.consumer_id}
        />
      )}
    </div>
  );
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .substring(0, 100);
}

export default ConsumerRegistrationPage;
